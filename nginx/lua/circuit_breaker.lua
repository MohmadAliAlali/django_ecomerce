--[[
  Cluster-wide circuit breaker via lua_shared_dict (all OpenResty workers share one zone).

  - incr() / get() on shared dict are atomic across workers: a trip on worker A is visible
    to workers B, C, D on the next P2C lookup.
  - Recovery: exponential backoff + HALF_OPEN canary (LB_CB_CANARY_RATE), not a hard 10s flip.

  States: CLOSED -> OPEN (mute) -> HALF_OPEN (trickle) -> CLOSED on success.
]]

local _M = {
	dict = nil,
	fail_threshold = 3,
	base_open_seconds = 10,
	max_open_seconds = 120,
	canary_rate = 0.01,
}

local function fail_key(node_id)
	return node_id .. ":cb:fail"
end

local function open_until_key(node_id)
	return node_id .. ":cb:open_until"
end

local function trip_key(node_id)
	return node_id .. ":cb:trips"
end

local function half_open_key(node_id)
	return node_id .. ":cb:half"
end

local function backoff_seconds(trip_count)
	local base = _M.base_open_seconds
	local exponent = math.min(math.max(trip_count - 1, 0), 6)
	local seconds = base * (2 ^ exponent)
	return math.min(seconds, _M.max_open_seconds)
end

function _M.init(shared_dict)
	_M.dict = shared_dict
	_M.fail_threshold = tonumber(os.getenv("LB_CB_FAIL_THRESHOLD")) or 3
	_M.base_open_seconds = tonumber(os.getenv("LB_CB_OPEN_SECONDS")) or 10
	_M.max_open_seconds = tonumber(os.getenv("LB_CB_MAX_OPEN_SECONDS")) or 120
	_M.canary_rate = tonumber(os.getenv("LB_CB_CANARY_RATE")) or 0.01
end

local function state(node_id)
	if not _M.dict or not node_id then
		return "closed"
	end
	local until_ts = _M.dict:get(open_until_key(node_id))
	if until_ts and ngx.now() < until_ts then
		return "open"
	end
	if until_ts and ngx.now() >= until_ts then
		_M.dict:delete(open_until_key(node_id))
		_M.dict:set(half_open_key(node_id), 1)
	end
	if _M.dict:get(half_open_key(node_id)) == 1 then
		return "half_open"
	end
	return "closed"
end

function _M.is_open(node_id)
	return state(node_id) == "open"
end

--- P2C eligibility: open = never; half_open = canary sample; closed = always.
function _M.allow_traffic(node_id)
	local st = state(node_id)
	if st == "open" then
		return false
	end
	if st == "half_open" then
		return math.random() < _M.canary_rate
	end
	return true
end

function _M.record_success(node_id)
	if not _M.dict or not node_id then
		return
	end
	_M.dict:delete(fail_key(node_id))
	_M.dict:delete(open_until_key(node_id))
	_M.dict:delete(half_open_key(node_id))
	_M.dict:delete(trip_key(node_id))
end

function _M.record_failure(node_id)
	if not _M.dict or not node_id then
		return
	end
	local st = state(node_id)
	if st == "half_open" then
		local trips = (_M.dict:incr(trip_key(node_id), 1, 0, 0) or 1)
		local open_for = backoff_seconds(trips)
		_M.dict:set(open_until_key(node_id), ngx.now() + open_for)
		_M.dict:delete(half_open_key(node_id))
		_M.dict:delete(fail_key(node_id))
		ngx.log(ngx.WARN, "circuit re-opened from half_open node=", node_id, " trips=", trips)
		return
	end
	if st == "open" then
		return
	end

	local failures, err = _M.dict:incr(fail_key(node_id), 1, 0, 0)
	if not failures then
		ngx.log(ngx.ERR, "circuit incr failed: ", err)
		return
	end
	if failures >= _M.fail_threshold then
		local trips = (_M.dict:incr(trip_key(node_id), 1, 0, 0) or 1)
		local open_for = backoff_seconds(trips)
		_M.dict:set(open_until_key(node_id), ngx.now() + open_for)
		_M.dict:delete(fail_key(node_id))
		ngx.log(ngx.WARN, "circuit open node=", node_id, " trips=", trips, " open_sec=", open_for)
	end
end

return _M
