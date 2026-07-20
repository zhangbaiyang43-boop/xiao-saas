import requests
import json

print("=== 测试登录接口 ===")
login_response = requests.post(
    "http://localhost:9898/api/v1/login",
    json={"phone": "13800138000", "code": "123456"}
)
print("登录响应:", login_response.text)

if login_response.status_code == 200:
    data = login_response.json()
    token = data["data"]["token"]
    print("\n获取到的Token:", token[:30] + "...")
    
    # 测试客户列表
    headers = {"Authorization": f"Bearer {token}"}
    print("\n=== 测试客户列表接口 ===")
    customers_response = requests.get(
        "http://localhost:9898/api/v1/customers",
        headers=headers
    )
    print("客户列表响应状态:", customers_response.status_code)
    print("客户列表响应:", customers_response.text)
