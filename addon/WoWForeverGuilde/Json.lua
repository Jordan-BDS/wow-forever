-- Encodeur JSON minimal, déterministe (clés triées), compatible avec le décodeur du site.
-- Un tableau Lua est un tableau JSON s'il est marqué par ns.Json.array ou si ses clés sont exactement 1..n.
local ADDON, ns = ...

local Json = {}
ns.Json = Json

local ARRAY = {}
Json.ARRAY = ARRAY

function Json.array(t)
  return setmetatable(t or {}, ARRAY)
end

local function isArray(t)
  if getmetatable(t) == ARRAY then return true end
  local n = #t
  if n == 0 then return false end
  local count = 0
  for _ in pairs(t) do count = count + 1 end
  return count == n
end

local ESCAPES = {
  ['"'] = '\\"', ["\\"] = "\\\\", ["\b"] = "\\b", ["\f"] = "\\f", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t",
}

local function escape(s)
  return (s:gsub('[%c"\\]', function(c)
    return ESCAPES[c] or string.format("\\u%04x", c:byte())
  end))
end

local function encodeNumber(n)
  if n ~= n or n == math.huge or n == -math.huge then return "null" end
  if math.floor(n) == n and math.abs(n) < 2 ^ 53 then return string.format("%d", n) end
  return string.format("%.14g", n)
end

local encode

local function encodeTable(t, out)
  if isArray(t) then
    out[#out + 1] = "["
    for i = 1, #t do
      if i > 1 then out[#out + 1] = "," end
      encode(t[i], out)
    end
    out[#out + 1] = "]"
    return
  end
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = tostring(k) end
  table.sort(keys)
  out[#out + 1] = "{"
  for i, key in ipairs(keys) do
    if i > 1 then out[#out + 1] = "," end
    local value = t[key]
    if value == nil then value = t[tonumber(key)] end
    out[#out + 1] = '"' .. escape(key) .. '":'
    encode(value, out)
  end
  out[#out + 1] = "}"
end

encode = function(value, out)
  local kind = type(value)
  if value == nil then out[#out + 1] = "null"
  elseif kind == "boolean" then out[#out + 1] = value and "true" or "false"
  elseif kind == "number" then out[#out + 1] = encodeNumber(value)
  elseif kind == "string" then out[#out + 1] = '"' .. escape(value) .. '"'
  elseif kind == "table" then encodeTable(value, out)
  else out[#out + 1] = "null" end
end

function Json.encode(value)
  local out = {}
  encode(value, out)
  return table.concat(out)
end
