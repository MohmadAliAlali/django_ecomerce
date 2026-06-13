--[[ Maps ingress URI prefixes to affinity workload bins (light / medium / heavy). ]]

local _M = {
	routes = {
		["/api/health"] = "light",
		["/api/products"] = "light",
		["/api/cart"] = "medium",
		["/api/orders"] = "medium",
		["/api/checkout"] = "heavy",
	},
	default_bin = "light",
}

function _M.resolve(uri)
	local path = uri or "/"
	local best = _M.default_bin
	local best_len = -1
	for prefix, bin in pairs(_M.routes) do
		if path:sub(1, #prefix) == prefix and #prefix > best_len then
			best_len = #prefix
			best = bin
		end
	end
	return best
end

return _M
