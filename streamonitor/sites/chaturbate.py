import re
import requests
import time
import random
from streamonitor.bot import Bot
from streamonitor.enums import Status

# Disable proxy
import os
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'


class Chaturbate(Bot):
    site = 'Chaturbate'
    siteslug = 'CB'

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 120
        self.sleep_on_error = 180
        
        # Create session and disable proxy
        self.session = requests.Session()
        self.session.trust_env = False
        
        # Update headers with Chaturbate-specific requirements
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://chaturbate.com/{username}/",
            "Origin": "https://chaturbate.com",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        
        self.consecutive_errors = 0
        self.last_request_time = 0
        self.min_request_interval = 20
        self.cookies_initialized = False
        
    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username
    
    def getVideoUrl(self):
        """Get the stream URL with proper format"""
        url = self.lastInfo.get('url', '')
        
        if not url:
            self.logger.error("No URL in lastInfo!")
            return None
            
        # Clean up the URL - remove escape characters
        url = url.replace('\\/', '/')
        
        self.logger.info(f"Raw stream URL: {url[:100]}")
        
        # Handle CMAF edge servers if indicated
        if self.lastInfo.get('cmaf_edge'):
            url = url.replace('playlist.m3u8', 'playlist_sfm4s.m3u8')
            url = re.sub('live-.+amlst', 'live-c-fhls/amlst', url)
            self.logger.info(f"CMAF adjusted URL: {url[:100]}")
        
        # Get the best resolution playlist
        selected = self.getWantedResolutionPlaylist(url)
        if selected:
            self.logger.info(f"Final URL: {selected[:100]}")
        else:
            self.logger.error("Failed to get resolution playlist!")
        return selected

    def _wait_for_rate_limit(self):
        """Ensure minimum time between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            jitter = random.uniform(1, 3)
            time.sleep(sleep_time + jitter)
        
        self.last_request_time = time.time()
    
    def _initialize_cookies(self):
        """Visit main page first to get cookies/tokens"""
        if self.cookies_initialized:
            return True
            
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            # Visit the room page first to get cookies
            room_url = f"https://chaturbate.com/{self.username}/"
            r = self.session.get(room_url, headers=headers, timeout=30)
            
            if r.status_code == 200:
                self.cookies_initialized = True
                # Store cookies for ffmpeg to use
                self.cookies = r.cookies
                return True
            else:
                return False
                
        except Exception:
            return False

    def getStatus(self):
        """Use AJAX endpoint with proper session handling"""
        self._wait_for_rate_limit()
        
        # Initialize cookies on first run
        if not self.cookies_initialized:
            if not self._initialize_cookies():
                self.consecutive_errors += 1
                return Status.ERROR
            time.sleep(2)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://chaturbate.com",
            "Referer": f"https://chaturbate.com/{self.username}/",
            "Connection": "keep-alive",
        }
        
        data = {
            "room_slug": self.username,
            "bandwidth": "high"
        }

        try:
            r = self.session.post(
                "https://chaturbate.com/get_edge_hls_url_ajax/",
                headers=headers,
                data=data,
                timeout=30
            )
            
            if r.status_code == 429:
                self.consecutive_errors += 1
                self.ratelimit = True
                self.sleep_on_error = min(900, 120 * (2 ** self.consecutive_errors))
                return Status.RATELIMIT
            
            if r.status_code == 403:
                self.cookies_initialized = False
                self.consecutive_errors += 1
                return Status.RATELIMIT
            
            if r.status_code != 200:
                self.consecutive_errors += 1
                return Status.ERROR
            
            try:
                self.lastInfo = r.json()
                room_status = self.lastInfo.get("room_status", "offline")
                
                if room_status == "public":
                    url = self.lastInfo.get("url", "")
                    if url:
                        # Update cookies from this request too
                        if r.cookies:
                            self.cookies.update(r.cookies)
                        self.consecutive_errors = 0
                        return Status.PUBLIC
                    else:
                        return Status.OFFLINE
                        
                elif room_status in ["private", "hidden"]:
                    return Status.PRIVATE
                else:
                    return Status.OFFLINE
                    
            except ValueError:
                self.consecutive_errors += 1
                return Status.ERROR
                
        except requests.exceptions.Timeout:
            self.consecutive_errors += 1
            return Status.ERROR
            
        except requests.exceptions.RequestException:
            self.consecutive_errors += 1
            self.cookies_initialized = False
            return Status.RATELIMIT
            
        except Exception:
            self.consecutive_errors += 1
            return Status.ERROR

        finally:
            self.ratelimit = False
            if self.consecutive_errors > 0:
                self.sleep_on_error = min(900, 120 * (2 ** self.consecutive_errors))