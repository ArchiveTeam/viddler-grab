wget.callbacks.httploop_result = function(url, err, http_stat)
  -- NEW for 2014: Slightly more verbose messages because people keep
  -- complaining that it's not moving or not working
  url_count = url_count + 1
  io.stdout:write(url_count .. "=" .. url["url"] .. ".  \r")
  io.stdout:flush()

  -- We're okay; sleep a bit (if we have to) and continue
  local sleep_time = 0.1 * (math.random(75, 125) / 100.0)


  if string.match(url["host"], "cdn")
  then
    -- We should be able to go fast on images since that's what a web browser does
    sleep_time = 0
  end

  if sleep_time > 0.001 then
    os.execute("sleep " .. sleep_time)
  end

  return wget.actions.NOTHING
end
