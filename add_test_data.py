import requests
import json

# 登录获取token
login_response = requests.post(
    "http://localhost:9898/api/v1/login",
    json={"phone": "13800138000", "code": "123456"}
)
data = login_response.json()
token = data["data"]["token"]
headers = {"Authorization": f"Bearer {token}"}

# 添加测试客户（需要openid）
test_customers = [
    {"openid": "mock_openid_1", "name": "张三", "phone": "13800138001", "tags": ["VIP"]},
    {"openid": "mock_openid_2", "name": "李四", "phone": "13800138002", "tags": ["普通会员"]},
    {"openid": "mock_openid_3", "name": "王五", "phone": "13800138003", "tags": ["高消费"]},
    {"openid": "mock_openid_4", "name": "赵六", "phone": "13800138004", "tags": ["新会员"]},
    {"openid": "mock_openid_5", "name": "钱七", "phone": "13800138005", "tags": ["VIP", "高消费"]},
]

for customer in test_customers:
    response = requests.post(
        "http://localhost:9898/api/v1/customers",
        json=customer,
        headers=headers
    )
    print(f"添加 {customer['name']}: {response.status_code} - {response.text}")

# 查询客户列表
response = requests.get(
    "http://localhost:9898/api/v1/customers",
    headers=headers
)
print("\n客户列表:")
print(response.text)
