local _M = {
	routes = {},
	max_compute = 2048,
	default_compute = 100,
}

function _M.load_from_atlas(data)
	_M.routes = data.routeCompute or {}
	_M.max_compute = tonumber(data.maxComputeUnits) or 2048
	_M.default_compute = tonumber(data.defaultComputeUnits) or 100
end

function _M.resolve(uri)
	local path = uri or "/"
	local best = nil
	local best_len = -1
	for prefix, units in pairs(_M.routes) do
		if path:sub(1, #prefix) == prefix and #prefix > best_len then
			best_len = #prefix
			best = tonumber(units)
		end
	end
	local load = best or _M.default_compute
	if load < 1 then
		load = 1
	end
	if load > _M.max_compute then
		load = _M.max_compute
	end
	return load
end

return _M
