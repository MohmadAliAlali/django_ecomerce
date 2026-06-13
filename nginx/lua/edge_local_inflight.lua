--[[
  Per-worker in-flight counter (Lua module state is isolated per OS worker process).
  Pads P2C scores between 300ms Redis pulls to reduce micro-burst blind routing on this worker.
]]

local _M = {
	counts = {},
}

function _M.on_route(node_id)
	if not node_id then
		return
	end
	_M.counts[node_id] = (_M.counts[node_id] or 0) + 1
end

function _M.on_complete(node_id)
	if not node_id then
		return
	end
	local current = _M.counts[node_id]
	if not current then
		return
	end
	current = current - 1
	if current <= 0 then
		_M.counts[node_id] = nil
	else
		_M.counts[node_id] = current
	end
end

function _M.local_penalty(node_id, max_active)
	local count = _M.counts[node_id] or 0
	if max_active <= 0 then
		return count
	end
	return count / max_active
end

return _M
