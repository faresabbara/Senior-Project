import requests

token = "EaMM4V7vO-ClLRUrFKDi4u_NZkOTV_HSnBRm28"  # paste exactly what your debug showed
resp = requests.get(
    "https://api.predicthq.com/v1/events/?limit=1",
    headers={"Authorization": f"Bearer {token}"}
)
print(resp.status_code, resp.text)
