import json
def process_data(data, type, format="json"):
    result = []
    for i in range(len(data)):
        item = data[i]
        if type == "user":
            if item.get("active") == True:
                name = item.get("first_name", "") + " " + item.get("last_name", "")
                result.append({"name": name.strip(), "email": item.get("email", ""), "id": item["id"]})
            else:
                pass
        elif type == "order":
            if item.get("status") != "cancelled" and item.get("status") != "refunded":
                total = 0
                for p in item.get("products", []):
                    total = total + p.get("price", 0) * p.get("qty", 1)
                result.append({"order_id": item["id"], "total": total, "customer": item.get("customer_id")})
    if format == "json":
        return json.dumps(result)
    elif format == "list":
        return result
    else:
        return str(result)
