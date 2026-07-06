"""Quick dev server for visual testing."""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from mops.api import MopsApi
from mops.stats import TrafficStats

async def main():
    api = MopsApi(port=4000, server_stats=TrafficStats(), mode="server")
    await api.run()
    print("Server running on http://127.0.0.1:4000")
    await asyncio.sleep(3600)

asyncio.run(main())
