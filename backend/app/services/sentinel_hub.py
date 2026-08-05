import httpx
import logging
from typing import Optional
from datetime import datetime, timezone
from app.config import settings

logger = logging.getLogger(__name__)

class SentinelHubService:
    """Service to interact with Sentinel Hub APIs."""
    
    def __init__(self):
        self.client_id = settings.SENTINEL_HUB_CLIENT_ID
        self.client_secret = settings.SENTINEL_HUB_CLIENT_SECRET
        self.process_api_key = settings.SENTINEL_HUB_PROCESS_API_KEY
        self.catalog_api_key = settings.SENTINEL_HUB_CATALOG_API_KEY
        self.statistics_api_key = settings.SENTINEL_HUB_STATISTICS_API_KEY
        self.base_url = settings.SENTINEL_HUB_BASE_URL
        self._token: Optional[str] = None
        self._token_expiry: Optional[float] = None
        
    async def _get_token(self) -> str:
        """Fetch and cache OAuth2 token from Sentinel Hub."""
        current_time = datetime.now(timezone.utc).timestamp()
        if self._token and self._token_expiry and current_time < self._token_expiry:
            return self._token
            
        url = f"{self.base_url}/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=data)
                response.raise_for_status()
                token_data = response.json()
                self._token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                # 60s buffer before actual expiration
                self._token_expiry = current_time + expires_in - 60 
                return self._token
            except httpx.HTTPError as e:
                logger.error(f"Failed to get Sentinel Hub token: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error getting Sentinel Hub token: {e}")
                raise

    async def _auth_headers(self, api_key: Optional[str] = None) -> dict[str, str]:
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def get_imagery(
        self, 
        bbox: list[float], 
        date: str, 
        evalscript: Optional[str], 
        width: int, 
        height: int, 
        format: str = "image/png"
    ) -> bytes:
        """Fetch satellite imagery using Process API."""
        url = f"{self.base_url}/api/v1/process"
        
        if not evalscript:
            evalscript = """
//VERSION=3
function setup() {
  return { input: ["B04", "B03", "B02"], output: { bands: 3 } };
}
function evaluatePixel(sample) {
  return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
}
            """
            
        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    }
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date}T00:00:00Z",
                                "to": f"{date}T23:59:59Z"
                            }
                        }
                    }
                ]
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {
                            "type": format
                        }
                    }
                ]
            },
            "evalscript": evalscript
        }
        
        headers = {
            **await self._auth_headers(self.process_api_key),
            "Content-Type": "application/json",
            "Accept": format
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
                return response.content
            except httpx.HTTPError as e:
                logger.error(f"Error fetching imagery from Process API: {e}")
                raise

    async def search_catalog(
        self, 
        bbox: list[float], 
        date_from: str, 
        date_to: str, 
        max_cloud_cover: float, 
        limit: int = 10
    ) -> dict:
        """Search Sentinel Hub Catalog API for available data."""
        url = f"{self.base_url}/api/v1/catalog/1.0.0/search"
        
        payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": bbox,
            "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
            "filter": {
                "op": "<",
                "args": [{"property": "eo:cloud_cover"}, max_cloud_cover * 100]
            },
            "limit": limit
        }
        
        headers = {
            **await self._auth_headers(self.catalog_api_key),
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=30.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error searching Catalog API: {e}")
                raise

    async def get_statistics(
        self, 
        geometry: dict, 
        date_from: str, 
        date_to: str, 
        evalscript: Optional[str], 
        interval: str = "P1D"
    ) -> dict:
        """Fetch statistics using Statistical API."""
        url = f"{self.base_url}/api/v1/statistics"
        
        if not evalscript:
            evalscript = """
//VERSION=3
function setup() {
  return { input: ["B04", "B08", "dataMask"], output: [{ id: "ndvi", bands: 1 }, { id: "dataMask", bands: 1 }] };
}
function evaluatePixel(samples) {
  let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
  return { ndvi: [ndvi], dataMask: [samples.dataMask] };
}
            """
            
        payload = {
            "input": {
                "bounds": {
                    "geometry": geometry,
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    }
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date_from}T00:00:00Z",
                                "to": f"{date_to}T23:59:59Z"
                            }
                        }
                    }
                ]
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{date_from}T00:00:00Z",
                    "to": f"{date_to}T23:59:59Z"
                },
                "aggregationInterval": {
                    "of": interval
                },
                "evalscript": evalscript,
                "resx": 10,
                "resy": 10
            }
        }
        
        headers = {
            **await self._auth_headers(self.statistics_api_key),
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error fetching statistics from Statistical API: {e}")
                raise
