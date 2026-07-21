import re

src_path = '/home/yapilwsl/arthityap/infra/codebase/mcp_codebase.py'
with open(src_path, 'r') as f:
    content = f.read()

# Check what we have
print('Has index_repository:', 'def index_repository(' in content)
print('Has delete_collection:', 'def delete_collection(' in content)
print('Has get_collection_stats_tool:', 'def get_collection_stats_tool(' in content)
print('Has @mcp.resource:', '@mcp.resource' in content)
print('Has @mcp.prompt:', '@mcp.prompt' in content)
print()

# Check search_codebase has collection param
search_match = re.search(r'def search_codebase\(([^)]+)\)', content)
if search_match:
    print('search_codebase params:', search_match.group(1).strip())
    
lines = content.split('\n')
print(f'Total lines: {len(lines)}')
