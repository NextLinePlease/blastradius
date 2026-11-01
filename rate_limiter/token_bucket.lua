local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2]) -- tokens regenerated per second
local now = tonumber(ARGV[3])  -- current timestamp in seconds
local requested = tonumber(ARGV[4])

-- Retrieve current state from Redis Hash
local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
local tokens = tonumber(bucket[1])
local last_update = tonumber(bucket[2])

-- Initialize if it doesn't exist
if not tokens then
    tokens = capacity
    last_update = now
end

-- Calculate tokens generated since the last request
local elapsed_time = math.max(0, now - last_update)
tokens = math.min(capacity, tokens + (elapsed_time * rate))

-- Evaluate the request
if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
    -- Auto-cleanup keys if the user stops sending requests
    redis.call('EXPIRE', key, math.ceil(capacity / rate) + 2)
    return 1 -- Allowed
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
    return 0 -- Rejected (Rate Limited)
end