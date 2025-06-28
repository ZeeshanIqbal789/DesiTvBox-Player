#!/usr/bin/env python3
"""
URL Extractor for TVNation - Bypass Restrictions
Extracts direct M3U8 URLs from embedded players to bypass domain restrictions
"""
import requests
import re
import json
from urllib.parse import unquote, parse_qs, urlparse
import trafilatura
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class TVNationExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def extract_from_tvnation(self, url_code):
        """Extract M3U8 URL from TVNation embedded player"""
        try:
            # Construct the TVNation URL
            tvnation_url = f"http://www.tvnation.me/flix.php?url={url_code}"
            logger.info(f"Extracting from: {tvnation_url}")
            
            # Try different referrer headers to bypass restrictions
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Referer': 'http://www.tvnation.me/',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Get the page content
            response = self.session.get(tvnation_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            print(f"Response status: {response.status_code}")
            print(f"Content length: {len(response.text)}")
            print(f"First 500 chars: {response.text[:500]}")
            
            # Parse with Beautiful Soup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for video sources in various formats
            m3u8_urls = []
            
            # Method 1: Look for direct M3U8 links in script tags
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Look for M3U8 URLs
                    m3u8_matches = re.findall(r'["\']([^"\']*\.m3u8[^"\']*)["\']', script.string)
                    m3u8_urls.extend(m3u8_matches)
                    
                    # Look for base64 encoded URLs
                    b64_matches = re.findall(r'["\']([A-Za-z0-9+/=]{50,})["\']', script.string)
                    for b64 in b64_matches:
                        try:
                            import base64
                            decoded = base64.b64decode(b64).decode('utf-8')
                            if '.m3u8' in decoded:
                                m3u8_urls.append(decoded)
                        except:
                            pass
            
            # Method 2: Look for video tags and source elements
            video_tags = soup.find_all('video')
            for video in video_tags:
                src = video.get('src')
                if src and '.m3u8' in src:
                    m3u8_urls.append(src)
                
                sources = video.find_all('source')
                for source in sources:
                    src = source.get('src')
                    if src and '.m3u8' in src:
                        m3u8_urls.append(src)
            
            # Method 3: Look for iframe sources
            iframes = soup.find_all('iframe')
            for iframe in iframes:
                src = iframe.get('src')
                if src:
                    # Try to extract from iframe content
                    try:
                        iframe_response = self.session.get(src, timeout=10)
                        iframe_m3u8 = re.findall(r'["\']([^"\']*\.m3u8[^"\']*)["\']', iframe_response.text)
                        m3u8_urls.extend(iframe_m3u8)
                    except:
                        pass
            
            # Method 4: Use trafilatura to extract text and look for URLs
            try:
                extracted_text = trafilatura.extract(response.text)
                if extracted_text:
                    text_m3u8 = re.findall(r'(https?://[^\s]+\.m3u8[^\s]*)', extracted_text)
                    m3u8_urls.extend(text_m3u8)
            except:
                pass
            
            # Clean and validate URLs
            valid_m3u8_urls = []
            for url in m3u8_urls:
                url = url.strip()
                if url and self.is_valid_m3u8_url(url):
                    valid_m3u8_urls.append(url)
            
            # Remove duplicates
            valid_m3u8_urls = list(set(valid_m3u8_urls))
            
            logger.info(f"Found {len(valid_m3u8_urls)} M3U8 URLs")
            return valid_m3u8_urls
            
        except Exception as e:
            logger.error(f"Error extracting from TVNation: {e}")
            return []
    
    def is_valid_m3u8_url(self, url):
        """Validate if URL is a proper M3U8 URL"""
        if not url or len(url) < 10:
            return False
        
        # Must contain .m3u8
        if '.m3u8' not in url.lower():
            return False
        
        # Must start with http
        if not url.startswith('http'):
            return False
        
        # Should not contain obvious placeholders
        placeholders = ['example.com', 'placeholder', 'dummy', 'test.m3u8']
        for placeholder in placeholders:
            if placeholder in url.lower():
                return False
        
        return True
    
    def test_m3u8_url(self, url):
        """Test if M3U8 URL is accessible"""
        try:
            response = self.session.head(url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def extract_and_validate(self, url_code):
        """Extract M3U8 URLs and test them"""
        m3u8_urls = self.extract_from_tvnation(url_code)
        
        if not m3u8_urls:
            return None, "No M3U8 URLs found in the embedded player"
        
        # Test each URL
        working_urls = []
        for url in m3u8_urls:
            if self.test_m3u8_url(url):
                working_urls.append(url)
                logger.info(f"Working M3U8 URL: {url}")
            else:
                logger.warning(f"Non-working M3U8 URL: {url}")
        
        if working_urls:
            return working_urls[0], f"Found {len(working_urls)} working URLs"
        else:
            return m3u8_urls[0] if m3u8_urls else None, "URLs found but may need authentication"

def extract_url_code_from_full_url(full_url):
    """Extract the URL code from a full TVNation URL"""
    if 'url=' in full_url:
        parsed = urlparse(full_url)
        params = parse_qs(parsed.query)
        return params.get('url', [None])[0]
    return full_url

if __name__ == "__main__":
    extractor = TVNationExtractor()
    
    # Test with the provided URL code
    url_code = "kxrOyaORnebzor2"
    m3u8_url, message = extractor.extract_and_validate(url_code)
    
    print(f"Result: {message}")
    if m3u8_url:
        print(f"M3U8 URL: {m3u8_url}")
    else:
        print("No valid M3U8 URL found")