import requests
from flask import Blueprint, request, Response, current_app

bp = Blueprint("ear", __name__)

EAR_SERVICE_URL = "http://localhost:5001"

@bp.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
@bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(path):
    """
    Reverse proxy to the independent EAR standalone service running on port 5001.
    All HTTP methods, headers, and body payloads (including files) are forwarded untouched. 
    """
    from flask import redirect

    # In production, the hosting provider (Nginx/Route53/etc.) handles the /ear/ routing directly 
    # to the standalone deployment container. We just issue a hard redirect if they somehow hit the Python instance.
    local_hosts = ['localhost', '127.0.0.1', '0.0.0.0']
    is_local = any(h in request.host for h in local_hosts)
    
    if not is_local:
        return redirect(f"https://jeremyzay.com/ear/{path}")

    target_url = f"{EAR_SERVICE_URL}/{path}"
    
    # Extract headers from the incoming client request to forward downstream
    headers = {key: value for (key, value) in request.headers if key != 'Host'}
    
    try:
        # Use a streaming payload proxy instead of downloading large ML files to RAM
        proxied_response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.form if request.form else request.get_data(),
            files=request.files,
            cookies=request.cookies,
            allow_redirects=False,
            stream=True
        )
        
        # Mirror the returned headers backwards from the EAR service to the client
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(n, v) for n, v in proxied_response.raw.headers.items()
                   if n.lower() not in excluded_headers]
                   
        return Response(
            proxied_response.iter_content(chunk_size=10*1024), 
            status=proxied_response.status_code, 
            headers=headers
        )
    except requests.exceptions.ConnectionError:
        return {"error": "The secondary ML service (EAR) is currently offline or offline. Please ensure it is running on Port 5001."}, 503
