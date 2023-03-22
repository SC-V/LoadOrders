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
    phone = phone.replace(" ", "").replace("-", "").replace("_", "").replace(".0", "")
    if len(phone) == 10 and not (phone.startswith("52") or phone.startswith("+52")):
        phone = "+52" + phone
    return phone


def create_order(barcode: str, comment: str, customer_address: str, fname: str, lname: str, phone: str, client: str):
    url = f"{URL}/create?dump=eventlog"
    normalized_phone = normalize(phone)
    payload = json.dumps({
        "info": {
            "operator_request_id": f"{barcode}",
            "comment": f"direccion original: {customer_address} | {comment}"
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
            comment=row['Comment'],
            customer_address=row['Address'],
            fname=row['Recipient'],
            lname="-",
            phone=row['Phone'],
            client=row['Client'])
        result.append([row['Address'], response, status_code])
    parsed_addresses = pd.DataFrame(result, columns=['Address', 'Response', 'RCode'])
    st.dataframe(parsed_addresses)
    print(parsed_addresses)


st.markdown(f"# Orders load and routing")

st.subheader("Load orders", anchor=None)
st.caption(f"Add orders here, then press upload button: {LOAD_LINK}", unsafe_allow_html=True)
if st.button("Upload from Google sheets", type="primary"):
    load_mex_wh_orders()

st.subheader("Get routing parameters", anchor=None)
country = "Mexico"
country_timezones = {
    "Mexico": "-06:00",
    "Chile": "-03:00",
    "UAE": "+03:00"
}
country_timezone = country_timezones[country]

interval_start, interval_end = st.select_slider(
    'Select delivery window',
    options=['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
             '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21',
             '22', '23', '24'],
    value=('00', '24'))

deliver_till = f"1970-01-02T00:00:00{country_timezone}" if interval_end == '24' else f"1970-01-01T{interval_end}:00:00{country_timezone}"
start_routing_at = f"1970-01-02T00:00:00{country_timezone}" if interval_start == '24' else f"1970-01-01T{interval_start}:00:00{country_timezone}"
pickup_till = start_routing_at

col_cour, col_unit, col_prox = st.columns(3, gap="medium")
with col_cour:
    couriers = st.number_input('Maximum number of couriers', value=10, min_value=0, max_value=3000, step=1)
with col_unit:
    units = st.number_input('Limit of orders per courier', value=35, min_value=0, max_value=500, step=1)
with col_prox:
    global_proximity_factor = st.number_input('Proximity factor', value=0.3, min_value=0.0, max_value=10.0, step=0.1)

col_qual, col_excl = st.columns(2, gap="medium")
with col_qual:
    quality = st.selectbox('Routing quality', ["normal", "low", "high"], index=0, help='Higher the quality, longer the routing time')
with col_excl:
    excluded_list = st.text_area('Claims to exclude from routing', height=200, help='Copy and paste from the route reports app if you need to exclude claims from routing')
    if excluded_list:
        excluded_list = excluded_list.split()

st.write('Delivery window from', interval_start, 'to', interval_end, f"{country} time (GMT{country_timezone}) –",
         str(int(interval_end) - int(interval_start)), f"hours, .\n",
         "Routing for no more than", str(couriers), "couriers, with maximum parcels per courier of", str(units))

routing_parameters = {
    "group_id": "chile sc",
    "routing_settings_overrides": {
        "quality": quality,
        "delivery_guarantees": {
            "start_routing_at": start_routing_at,
            "pickup_till": pickup_till,
            "deliver_till": deliver_till
        },
        "copy_fake_courier": {
            "count": couriers,
            "courier_pattern": {"units": units}
        },
        "global_proximity_factor": global_proximity_factor
    }
}

if excluded_list:
    routing_parameters["excluded_claims"] = excluded_list

routing_parameters = json.dumps(routing_parameters, indent=2)
st.code(routing_parameters, language="json")
