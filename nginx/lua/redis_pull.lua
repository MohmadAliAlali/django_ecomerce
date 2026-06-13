--[[ Background-only Redis client: never call from the request hot path. ]]

local redis = require "resty.redis"
local cjson = require "cjson.safe"

local _M = {}

local BIN_NAMES = { "light", "medium", "heavy" }

local function connect()
	local host = os.getenv("REDIS_HOST") or "redis"
	local port = tonumber(os.getenv("REDIS_PORT")) or 6379
	local red = redis:new()
	red:set_timeout(100)
	local ok, err = red:connect(host, port)
	if not ok then
		return nil, err
	end
	return red
end

--- @return table<string, table>|nil snapshot map nodeId -> live fields
function _M.fetch_live_snapshot(node_ids)
	local red, err = connect()
	if not red then
		return nil, err
	end

	local snapshot = {}
	for _, node_id in ipairs(node_ids) do
		local key = "lb:live:" .. node_id
		local res, rerr = red:hmget(
			key,
			"active",
			"ewmaRtMs",
			"online",
			"updatedAt",
			"maxActive",
			"targetRtMs",
			"serverTier"
		)
		if res and res[1] then
			snapshot[node_id] = {
				active = tonumber(res[1]) or 0,
				ewma = tonumber(res[2]) or 0,
				online = res[3] == "1",
				updatedAt = tonumber(res[4]) or 0,
				maxActive = tonumber(res[5]) or 0,
				targetRtMs = tonumber(res[6]) or 0,
				serverTier = res[7] or "",
			}
		elseif rerr then
			ngx.log(ngx.DEBUG, "hmget failed for ", node_id, ": ", rerr)
		end
	end

	red:set_keepalive(10000, 50)
	return snapshot
end

--- @return table<string, string[]>|nil binName -> node ids
function _M.fetch_bin_members()
	local red, err = connect()
	if not red then
		return nil, err
	end

	local bins = {}
	for _, bin in ipairs(BIN_NAMES) do
		local key = "lb:bin:" .. bin
		local members, merr = red:smembers(key)
		if members then
			bins[bin] = members
		elseif merr then
			ngx.log(ngx.DEBUG, "smembers failed for ", key, ": ", merr)
			bins[bin] = {}
		end
	end

	red:set_keepalive(10000, 50)
	return bins
end

function _M.scrub_ghost_from_bin(node_id, bin_name)
	if not node_id or not bin_name then
		return
	end
	local red, err = connect()
	if not red then
		ngx.log(ngx.WARN, "ghost scrub connect failed: ", err or "unknown")
		return
	end
	local key = "lb:bin:" .. bin_name
	local _, serr = red:srem(key, node_id)
	if serr then
		ngx.log(ngx.WARN, "ghost scrub srem failed: ", serr)
	end
	red:set_keepalive(10000, 50)
end

function _M.encode_members(ids)
	return table.concat(ids or {}, ",")
end

function _M.decode_members(raw)
	if not raw or raw == "" then
		return {}
	end
	local out = {}
	for id in string.gmatch(raw, "[^,]+") do
		out[#out + 1] = id
	end
	return out
end

return _M
