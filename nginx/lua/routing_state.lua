local cjson = require "cjson.safe"
local route_compute = require "route_compute"
local route_bin = require "route_bin"
local live_cache = require "live_cache"
local circuit_breaker = require "circuit_breaker"
local edge_local_inflight = require "edge_local_inflight"

local _M = {
	bins = {},
	fallback_candidates = { { id = "fallback", upstream = "http://app1:8080" } },
	atlas_path = nil,
	upstreams = {},
}

local function pick_two_random_ids(member_ids)
	if #member_ids == 0 then
		return nil, nil
	end
	if #member_ids == 1 then
		return member_ids[1], nil
	end
	local i = math.random(#member_ids)
	local j = math.random(#member_ids)
	if j == i then
		j = (j % #member_ids) + 1
	end
	return member_ids[i], member_ids[j]
end

local function pick_two_random(candidates)
	if #candidates == 0 then
		return nil
	end
	if #candidates == 1 then
		return candidates[1]
	end
	local i = math.random(#candidates)
	local j = math.random(#candidates)
	if j == i then
		j = (j % #candidates) + 1
	end
	return candidates[i], candidates[j]
end

local function filter_eligible(candidates)
	local out = {}
	for _, c in ipairs(candidates) do
		if circuit_breaker.allow_traffic(c.id) and live_cache.is_available(c.id) then
			out[#out + 1] = c
		end
	end
	if #out == 0 then
		for _, c in ipairs(candidates) do
			if circuit_breaker.allow_traffic(c.id) then
				out[#out + 1] = c
			end
		end
	end
	if #out == 0 then
		return candidates
	end
	return out
end

local function members_to_candidates(member_ids, workload_bin)
	local out = {}
	for _, id in ipairs(member_ids) do
		if not live_cache.has_heartbeat(id) then
			live_cache.schedule_ghost_scrub(id, workload_bin)
		elseif circuit_breaker.allow_traffic(id) then
			out[#out + 1] = { id = id, upstream = live_cache.upstream_for(id) }
		end
	end
	return out
end

local function normalize_candidates(route)
	if route.candidates and #route.candidates > 0 then
		return route.candidates
	end
	if route.upstreams and #route.upstreams > 0 then
		local out = {}
		for _, u in ipairs(route.upstreams) do
			out[#out + 1] = { id = u, upstream = u }
		end
		return out
	end
	if route.upstream then
		return { { id = route.upstream, upstream = route.upstream } }
	end
	return nil
end

local function index_upstreams(candidates)
	for _, c in ipairs(candidates or {}) do
		if c.id and c.upstream then
			_M.upstreams[c.id] = c.upstream
		end
	end
end

local function collect_all_node_ids()
	local ids = {}
	local seen = {}
	local function add_from(candidates)
		for _, c in ipairs(candidates) do
			if c.id and not seen[c.id] then
				seen[c.id] = true
				ids[#ids + 1] = c.id
			end
		end
	end
	add_from(_M.fallback_candidates)
	for _, bin in ipairs(_M.bins) do
		add_from(bin.candidates)
	end
	return ids
end

local function load_from_file(path)
	local f, err = io.open(path, "r")
	if not f then
		return false, "open failed: " .. (err or "unknown")
	end
	local body = f:read("*a")
	f:close()
	local data, jerr = cjson.decode(body)
	if not data then
		return false, "json: " .. (jerr or "unknown")
	end

	route_compute.load_from_atlas(data)

	local routes = {}
	for _, route in ipairs(data.routes or {}) do
		local candidates = normalize_candidates(route)
		if candidates then
			index_upstreams(candidates)
			routes[#routes + 1] = {
				min = route.minInclusive,
				max = route.maxExclusive,
				candidates = candidates,
			}
		end
	end
	_M.bins = routes

	if data.fallbackCandidates and #data.fallbackCandidates > 0 then
		_M.fallback_candidates = data.fallbackCandidates
		index_upstreams(_M.fallback_candidates)
	elseif data.fallbackUpstreams and #data.fallbackUpstreams > 0 then
		local out = {}
		for _, u in ipairs(data.fallbackUpstreams) do
			out[#out + 1] = { id = u, upstream = u }
		end
		_M.fallback_candidates = out
		index_upstreams(out)
	end

	live_cache.set_node_ids(collect_all_node_ids())
	live_cache.set_upstreams(_M.upstreams)
	return true
end

function _M.reload(path)
	local ok, err = load_from_file(path)
	if not ok then
		ngx.log(ngx.WARN, "routing_state reload failed: ", err)
		return false
	end
	return true
end

local function p2c_pick(candidates)
	local pool = filter_eligible(candidates)
	if #pool == 0 then
		return nil, nil
	end
	if #pool == 1 then
		return pool[1].upstream, pool[1].id
	end

	local a, b = pick_two_random(pool)
	if not b then
		return a.upstream, a.id
	end

	local sa = live_cache.load_score(a.id, "medium")
	local sb = live_cache.load_score(b.id, "medium")
	if sa <= sb then
		return a.upstream, a.id
	end
	return b.upstream, b.id
end

local function p2c_pick_bin(workload_bin, member_ids, allow_escalation)
	local threshold = tonumber(os.getenv("LB_FALLBACK_SCORE_THRESHOLD")) or 1.5
	for _ = 1, 6 do
		local id_a, id_b = pick_two_random_ids(member_ids)
		if not id_a then
			return nil, nil, false
		end
		if not live_cache.has_heartbeat(id_a) then
			live_cache.schedule_ghost_scrub(id_a, workload_bin)
		elseif not id_b then
			if circuit_breaker.allow_traffic(id_a) then
				return live_cache.upstream_for(id_a), id_a, false
			end
		elseif not live_cache.has_heartbeat(id_b) then
			live_cache.schedule_ghost_scrub(id_b, workload_bin)
		elseif circuit_breaker.allow_traffic(id_a) and circuit_breaker.allow_traffic(id_b) then
			local sa = live_cache.load_score(id_a, workload_bin)
			local sb = live_cache.load_score(id_b, workload_bin)

			if allow_escalation
				and workload_bin == "light"
				and sa > threshold
				and sb > threshold then
				return nil, nil, true
			end

			if sa <= sb then
				return live_cache.upstream_for(id_a), id_a, false
			end
			return live_cache.upstream_for(id_b), id_b, false
		end
	end
	return nil, nil, false
end

function _M.resolve_affinity(uri)
	local workload_bin = route_bin.resolve(uri)
	local members = live_cache.get_bin_members(workload_bin)

	if not members or #members == 0 then
		local load = route_compute.resolve(uri)
		return _M.resolve(load)
	end

	local upstream, node_id, escalate = p2c_pick_bin(workload_bin, members, true)
	if escalate then
		local heavy_members = live_cache.get_bin_members("heavy")
		if heavy_members and #heavy_members > 0 then
			upstream, node_id, _ = p2c_pick_bin("heavy", heavy_members, false)
			ngx.ctx.lb_escalated = true
		end
	end

	if not upstream then
		local candidates = members_to_candidates(members, workload_bin)
		upstream, node_id = p2c_pick(candidates)
	end

	ngx.ctx.lb_node_id = node_id
	ngx.ctx.lb_workload_bin = workload_bin
	if node_id then
		edge_local_inflight.on_route(node_id)
	end
	return upstream
end

function _M.resolve(load)
	local upstream, node_id = nil, nil
	local bins = _M.bins
	if #bins == 0 then
		upstream, node_id = p2c_pick(_M.fallback_candidates)
	else
		local lo, hi = 1, #bins
		while lo <= hi do
			local mid = math.floor((lo + hi) / 2)
			local bin = bins[mid]
			if load < bin.min then
				hi = mid - 1
			elseif load >= bin.max then
				lo = mid + 1
			else
				upstream, node_id = p2c_pick(bin.candidates)
				break
			end
		end
		if not upstream then
			if hi >= 1 then
				upstream, node_id = p2c_pick(bins[hi].candidates)
			else
				upstream, node_id = p2c_pick(bins[#bins].candidates)
			end
		end
	end

	ngx.ctx.lb_node_id = node_id
	if node_id then
		edge_local_inflight.on_route(node_id)
	end
	return upstream
end

function _M.resolve_route(uri)
	return route_compute.resolve(uri)
end

function _M.init(atlas_path, atlas_reload_sec, live_dict, circuit_dict, live_pull_sec)
	math.randomseed(ngx.now() * 10000 + ngx.worker.pid())
	_M.atlas_path = atlas_path

	live_cache.init(live_dict, live_pull_sec)
	circuit_breaker.init(circuit_dict)

	_M.reload(atlas_path)
	live_cache.pull_from_redis()

	ngx.timer.every(atlas_reload_sec, function(premature)
		if premature then
			return
		end
		_M.reload(atlas_path)
	end)
end

return _M
