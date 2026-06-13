--[[ Pull-and-cache live registry + affinity bin arrays: Redis on timer only. ]]

local redis_pull = require "redis_pull"

local _M = {
	dict = nil,
	node_ids = {},
	upstreams = {},
	max_active = 64,
	target_rt_ms = 200,
	affinity_match = 0.4,
	affinity_mismatch = -0.2,
	fallback_threshold = 1.5,
	last_pull_ok = 0,
}

local BIN_NAMES = { "light", "medium", "heavy" }

local function key(node_id, field)
	return node_id .. ":" .. field
end

local function bin_key(bin_name)
	return "bin:" .. bin_name
end

local function affinity_bonus(tier, workload_bin)
	if not tier or tier == "" or not workload_bin then
		return 0
	end
	local native = ({
		SMALL = "light",
		MEDIUM = "medium",
		MONSTER = "heavy",
	})[tier]
	if native == workload_bin then
		return _M.affinity_match
	end
	if tier == "MONSTER" and workload_bin == "light" then
		return _M.affinity_mismatch
	end
	return 0
end

function _M.init(shared_dict, pull_interval_sec)
	_M.dict = shared_dict
	_M.max_active = tonumber(os.getenv("LB_MAX_ACTIVE_REQUESTS")) or 64
	_M.target_rt_ms = tonumber(os.getenv("LB_TARGET_RESPONSE_TIME_MS")) or 200
	_M.affinity_match = tonumber(os.getenv("LB_AFFINITY_BONUS_MATCH")) or 0.4
	_M.affinity_mismatch = tonumber(os.getenv("LB_AFFINITY_BONUS_MISMATCH")) or -0.2
	_M.fallback_threshold = tonumber(os.getenv("LB_FALLBACK_SCORE_THRESHOLD")) or 1.5

	local interval = tonumber(os.getenv("LB_LIVE_PULL_INTERVAL_SEC")) or pull_interval_sec or 0.3

	local ok, err = ngx.timer.every(interval, function(premature)
		if premature then
			return
		end
		_M.pull_from_redis()
	end)
	if not ok then
		ngx.log(ngx.ERR, "live_cache timer failed: ", err)
	end
end

function _M.set_node_ids(ids)
	_M.node_ids = ids or {}
end

function _M.set_upstreams(map)
	_M.upstreams = map or {}
end

function _M.upstream_for(node_id)
	return _M.upstreams[node_id] or ("http://" .. node_id .. ":8080")
end

function _M.pull_from_redis()
	if not _M.dict then
		return
	end

	if #_M.node_ids > 0 then
		local snapshot, err = redis_pull.fetch_live_snapshot(_M.node_ids)
		if snapshot then
			local now = ngx.now()
			for node_id, data in pairs(snapshot) do
				_M.dict:set(key(node_id, "active"), data.active)
				_M.dict:set(key(node_id, "ewma"), data.ewma)
				_M.dict:set(key(node_id, "online"), data.online and 1 or 0)
				_M.dict:set(key(node_id, "updatedAt"), data.updatedAt)
				local max_a = data.maxActive > 0 and data.maxActive or _M.max_active
				local target = data.targetRtMs > 0 and data.targetRtMs or _M.target_rt_ms
				_M.dict:set(key(node_id, "maxActive"), max_a)
				_M.dict:set(key(node_id, "targetRt"), target)
				_M.dict:set(key(node_id, "tier"), data.serverTier or "")
				_M.dict:set(key(node_id, "alive"), 1)
			end
			for _, node_id in ipairs(_M.node_ids) do
				if not snapshot[node_id] then
					_M.dict:set(key(node_id, "alive"), 0)
					_M.dict:set(key(node_id, "online"), 0)
				end
			end
			_M.dict:set("_snapshot_at", now)
			_M.last_pull_ok = now
		else
			ngx.log(ngx.WARN, "live_cache redis pull failed: ", err or "unknown")
		end
	end

	local bins, berr = redis_pull.fetch_bin_members()
	if bins then
		for _, bin in ipairs(BIN_NAMES) do
			local members = bins[bin] or {}
			_M.dict:set(bin_key(bin), redis_pull.encode_members(members))
		end
	elseif berr then
		ngx.log(ngx.WARN, "live_cache bin pull failed: ", berr)
	end
end

function _M.get_bin_members(bin_name)
	if not _M.dict then
		return {}
	end
	local raw = _M.dict:get(bin_key(bin_name))
	return redis_pull.decode_members(raw)
end

function _M.has_heartbeat(node_id)
	if not _M.dict then
		return true
	end
	return _M.dict:get(key(node_id, "alive")) == 1
end

function _M.schedule_ghost_scrub(node_id, bin_name)
	ngx.timer.at(0, function(premature)
		if premature then
			return
		end
		redis_pull.scrub_ghost_from_bin(node_id, bin_name)
	end)
end

function _M.load_score(node_id, workload_bin)
	if not _M.dict then
		return math.huge
	end
	if not _M.has_heartbeat(node_id) then
		return math.huge
	end
	if _M.dict:get(key(node_id, "online")) ~= 1 then
		return math.huge
	end

	local max_a = _M.dict:get(key(node_id, "maxActive")) or _M.max_active
	local target = _M.dict:get(key(node_id, "targetRt")) or _M.target_rt_ms
	local active = _M.dict:get(key(node_id, "active")) or 0
	local ewma = _M.dict:get(key(node_id, "ewma")) or 0
	if ewma <= 0 then
		ewma = target
	end

	local active_part = max_a > 0 and (active / max_a) or active
	local rt_part = target > 0 and (ewma / target) or 1.0

	local edge_local = require "edge_local_inflight"
	local local_part = edge_local.local_penalty(node_id, max_a)

	local tier = _M.dict:get(key(node_id, "tier")) or ""
	local bonus = affinity_bonus(tier, workload_bin)

	return active_part + rt_part + local_part - bonus
end

function _M.is_available(node_id)
	return _M.has_heartbeat(node_id) and _M.dict and _M.dict:get(key(node_id, "online")) == 1
end

return _M
