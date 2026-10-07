from api_gateway.router import route_request

if __name__ == "__main__":
    response = route_request("/student/profile", {"id": "123"})
    print(response)
