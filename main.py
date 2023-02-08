import requests
import json
import pandas as pd
import streamlit as st
from io import BytesIO

ORD_SHEET_ID = st.secrets["ORD_SHEET_ID"]
URL = st.secrets["URL"]
API_KEYS = st.secrets["API_KEYS"]
STATIONS = st.secrets["STATIONS"]
LOAD_LINK = st.secrets["LOAD_LINK"]

def read_orders_frame() -> pd.DataFrame:
    request = requests.get(f'https://docs.google.com/spreadsheets/d/{ORD_SHEET_ID}/export?gid=0&format=csv',
                           verify=False)
    orders_in_csv = request.content
    orders_to_load = pd.read_csv(BytesIO(orders_in_csv), index_col=0).reset_index()
    print(orders_to_load)
    return orders_to_load


def normalize(phone: str):
    phone = str(phone)
    if len(phone) == 10 and not (phone.startswith("52") or phone.startswith("+52")):
        phone = "+52" + phone
    return phone


def create_order(barcode: str, comment: str, customer_address: str, fname: str, lname: str, phone: str, client: str):
    url = f"{URL}/create?dump=eventlog"
    normalized_phone = normalize(phone)
    payload = json.dumps({
        "info": {
            "operator_request_id": f"WH-{barcode}",
            "comment": comment
        },
        "last_mile_policy": "time_interval",
        "source": {
            "platform_station": {
                "platform_id": STATIONS[client]
            }
        },
        "destination": {
            "type": "custom_location",
            "custom_location": {
                "details": {
                    "full_address": customer_address.replace("#", "").replace("º", "").replace(",,", ",")
                }
            }
        },
        "items": [
            {
                "count": 1,
                "name": "Order",
                "article": f"{barcode}",
                "barcode": f"{barcode}",
                "billing_details": {
                    "unit_price": 0,
                    "assessed_unit_price": 0,
                    "currency": "MXN"
                },
                "physical_dims": {
                    "predefined_volume": 800,
                    "weight_gross": 150
                },
                "place_barcode": f"{barcode}"
            }
        ],
        "places": [
            {
                "physical_dims": {
                    "predefined_volume": 800
                },
                "description": "Yango Delivery almacen orden",
                "barcode": f"{barcode}"
            }
        ],
        "billing_info": {
            "payment_method": "already_paid"
        },
        "recipient_info": {
            "first_name": fname,
            "last_name": lname,
            "phone": normalized_phone
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {API_KEYS[client]}"
    }
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
    except:
        print("Failed to create order with unknown error")
        return "Failed to create order with unknown error", 500
    print("CREATE")
    print(response.headers)
    print(response.text)
    if response.status_code != 200:
        return response.text, response.status_code
    data = json.loads(response.text)
    print(data)
    offer_to_approve = data['offers'][0]['offer_id']
    print(offer_to_approve)
    url = f"{URL}/confirm"
    payload = json.dumps({
        "offer_id": offer_to_approve
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {API_KEYS[client]}"  # Set "Bearer <TOKEN> here"
    }
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
    except:
        print("Failed to approve order with unknown error")
        return "Failed to approve order with unknown error", 500
    print("CONFIRM")
    print(response.headers)
    print(response.text)
    return response.text, response.status_code


def load_mex_wh_orders():
    all_orders = read_orders_frame()
    result = []
    for index, row in all_orders.iterrows():
        print(f"ADDRESS: {row['Address']}")
        response, status_code = create_order(
            barcode=row['Barcode'],
            comment="Yango Warehouse order",
            customer_address=row['Address'],
            fname=row['Recipient'],
            lname="-",
            phone=row['Phone'],
            client=row['Client'])
        result.append([row['Address'], response, status_code])
    parsed_addresses = pd.DataFrame(result, columns=['Address', 'Response', 'RCode'])
    st.dataframe(parsed_addresses)
    print(parsed_addresses)


st.markdown(f"# Load orders")
st.caption(f"Add orders here, then press upload button: {LOAD_LINK}", unsafe_allow_html=True)
if st.sidebar.button("Upload from Google sheets", type="primary"):
    load_mex_wh_orders()
