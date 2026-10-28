-- Base64 standard (alphabet A-Z a-z 0-9 + /, remplissage =), sans opérateurs binaires : Lua 5.1 du jeu.
local ADDON, ns = ...

local Base64 = {}
ns.Base64 = Base64

local ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local CHARS = {}
for i = 1, 64 do CHARS[i - 1] = ALPHABET:sub(i, i) end

function Base64.encode(data)
  local out, n = {}, #data
  local floor = math.floor
  for i = 1, n, 3 do
    local a, b, c = data:byte(i, i + 2)
    local triple = a * 65536 + (b or 0) * 256 + (c or 0)
    local c1 = floor(triple / 262144)
    local c2 = floor(triple / 4096) % 64
    local c3 = floor(triple / 64) % 64
    local c4 = triple % 64
    out[#out + 1] = CHARS[c1] .. CHARS[c2] .. (b and CHARS[c3] or "=") .. (c and CHARS[c4] or "=")
  end
  return table.concat(out)
end
