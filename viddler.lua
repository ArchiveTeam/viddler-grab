local url_count = 0

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

  if (string.match(url["path"], "%.flv") or string.match(url["path"], "%.mp4"))
  and http_stat["statcode"] == 403 then
    io.stdout:write("Error: Got 403 on a video download.")
    io.stdout:flush()
    return wget.actions.ABORT
  end

  return wget.actions.NOTHING
end


wget.callbacks.get_urls = function(file, url, is_css, iri)
  local urls = {}

  if string.match(url, "com/embed/[a-fA-F0-9]+") then
    local video_id = string.match(url, "com/embed/([a-fA-F0-9]+)")
    
    local video_url = 'http://www.viddler.com/file/'..video_id..'html5'

    table.insert(urls, {
      url=video_url
    })

    local command = './riddler.py --wget '.. video_id
    io.stdout:write("\n")
    io.stdout:flush()

    local file = assert(io.popen(command, 'r'))
    local video_urls = file:read('*all')
    file:close()

    for video_url in video_urls:gmatch("%S+") do
      io.stdout:write(" Got video URL '"..video_url.."'\n")
      io.stdout:flush()

      table.insert(urls, {
        url=video_url
      })

      video_found = true
    end
  end

  return urls
end