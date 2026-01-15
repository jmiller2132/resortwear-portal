import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
from datetime import date, datetime
import re
import uuid
import requests
from urllib.parse import quote
import json

# Page configuration
st.set_page_config(
    page_title="Eagle Resort Wear Portal",
    page_icon="👕",
    layout="wide"
)

# Initialize session state
if 'order_data' not in st.session_state:
    st.session_state.order_data = {
        'header': {
            'sales_rep': None,
            'customer': None,
            'order_date': date.today(),
            'ship_date': None,
            'drop_dead_date': None,
            'po_number': '',
            'tax_status': 'Taxable',
            'tags': 'No',
            'delivery_method': 'Standard Ground Shipping',
            'notes': '',
            'shipping_address1': '',
            'shipping_address2': '',
            'shipping_city': '',
            'shipping_state': '',
            'shipping_zip': '',
            'billing_address1': '',
            'billing_address2': '',
            'billing_city': '',
            'billing_state': '',
            'billing_zip': '',
            'same_as_shipping': False
        },
        'grid': [],  # List of dictionaries: [{'SKU': '', 'Brand': '', 'Description': '', 'Color': '', 'XS': 0, 'S': 0, 'M': 0, 'L': 0, 'XL': 0, '2XL': 0, '3XL': 0, '4XL': 0, 'RowTotal': 0}],
        'decoration': {
            'design_type': 'New Design',  # 'New Design' or 'Re-Order'
            'reference_order_number': '',
            'method': 'Screenprint',
            'design1_number': '',
            'design1_location': '',
            'design1_description': '',
            'design1_colors': '',
            'design1_let_designers_pick': False,
            'design2_number': '',
            'design2_location': '',
            'design2_description': '',
            'design2_colors': '',
            'design2_let_designers_pick': False,
            'design2_premium_4color': False,
            'has_second_design': False,
            'confetti': False,
            'premium_4color': False,
            'art_setup_hours': 0.0
        }
    }

# Initialize view mode and review state
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'new_order'  # Default to new order screen
if 'show_order_review' not in st.session_state:
    st.session_state.show_order_review = False
if 'order_submitted' not in st.session_state:
    st.session_state.order_submitted = False

# Base URL for Google Sheets CSV export
# NOTE: This method requires the Google Sheet to be publicly accessible
# Go to Google Sheets → Share → "Change to anyone with the link" → Viewer
GSHEETS_BASE_URL = "https://docs.google.com/spreadsheets/d/14DYELQWKuQefjFEpTaltaS5YHhXeiIhr-QJ327mGwt0/gviz/tq?tqx=out:csv&sheet="

# Helper function to load and validate data
@st.cache_data(ttl=300)
def load_sheet_data(sheet_name):
    """Load data from Google Sheets with validation"""
    try:
        url = GSHEETS_BASE_URL + sheet_name
        df = pd.read_csv(url)
        df = df.fillna("")
        # Strip whitespace from string columns
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip()
        return df
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            st.error(f"⚠️ **{sheet_name} sheet is private.** Please make your Google Sheet public:\n1. Open the Google Sheet\n2. Click 'Share' button\n3. Click 'Change to anyone with the link'\n4. Set permission to 'Viewer'\n5. Click 'Done'")
        else:
            st.error(f"Error loading {sheet_name}: {error_msg}")
        return pd.DataFrame()

# Load all required sheets
products_df = load_sheet_data("Products")
customers_df = load_sheet_data("Customers")
salesreps_df = load_sheet_data("SalesReps")
# Note: Orders are stored in session state for now (can be extended to Google Sheets API)

# Ensure SalesReps has the expected structure if empty
if salesreps_df.empty:
    salesreps_df = pd.DataFrame(columns=['SalesRep', 'Customer', 'PIN'])

# Initialize session ID for logging
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

# Logging Helper Functions
def get_client_ip():
    """Extract client IP address from Streamlit request"""
    try:
        # Try to get IP from headers (works on Streamlit Cloud)
        if hasattr(st, 'request') and st.request:
            headers = st.request.headers
            # Check for forwarded IP (common in cloud deployments)
            forwarded = headers.get('X-Forwarded-For', '')
            if forwarded:
                return forwarded.split(',')[0].strip()
            # Fallback to other headers
            real_ip = headers.get('X-Real-Ip', '')
            if real_ip:
                return real_ip
        return 'Unknown'
    except Exception:
        return 'Unknown'

def get_user_agent():
    """Get browser/device information from User-Agent header"""
    try:
        if hasattr(st, 'request') and st.request:
            user_agent = st.request.headers.get('User-Agent', 'Unknown')
            # Parse basic info from user agent
            if 'Chrome' in user_agent:
                browser = 'Chrome'
            elif 'Firefox' in user_agent:
                browser = 'Firefox'
            elif 'Safari' in user_agent:
                browser = 'Safari'
            elif 'Edge' in user_agent:
                browser = 'Edge'
            else:
                browser = 'Other'
            
            if 'Windows' in user_agent:
                os = 'Windows'
            elif 'Mac' in user_agent or 'iPhone' in user_agent:
                os = 'Mac/iOS'
            elif 'Android' in user_agent:
                os = 'Android'
            elif 'Linux' in user_agent:
                os = 'Linux'
            else:
                os = 'Unknown'
            
            return f"{browser} on {os}"
        return 'Unknown'
    except Exception:
        return 'Unknown'

def generate_submission_number():
    """Generate unique submission number for orders (rolling integer starting at 1001)"""
    # Initialize submission counter if not exists
    if 'submission_counter' not in st.session_state:
        st.session_state.submission_counter = 1000  # Start at 1000, first will be 1001
    
    # Increment counter
    st.session_state.submission_counter += 1
    return f"#{st.session_state.submission_counter}"

def append_log_to_sheet(timestamp, ip_address, device, rep_name, event_type, status, details, session_id, order_number=""):
    """Append log entry to Google Sheets ActivityLogs sheet"""
    try:
        # Store log in session state for potential batch writing
        if 'pending_logs' not in st.session_state:
            st.session_state.pending_logs = []
        
        log_entry = {
            'Timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'IP Address': ip_address,
            'Device': device,
            'Rep Name': rep_name,
            'Event Type': event_type,
            'Status': status,
            'Details': details,
            'Session ID': session_id,
            'Order Number': order_number
        }
        
        st.session_state.pending_logs.append(log_entry)
        
        return True
    except Exception as e:
        # Silently fail logging to not disrupt user experience
        return False

def log_event(event_type, status, details="", order_number=""):
    """Main logging function"""
    try:
        timestamp = datetime.now()
        ip_address = get_client_ip()
        device = get_user_agent()
        rep_name = st.session_state.get('authenticated_rep', 'Unknown')
        session_id = st.session_state.get('session_id', 'Unknown')
        
        append_log_to_sheet(timestamp, ip_address, device, rep_name, event_type, status, details, session_id, order_number)
    except Exception:
        pass  # Silently fail to not disrupt app

# Helper functions
def get_available_skus():
    """Get list of available SKUs from Products sheet"""
    if products_df.empty:
        return []
    sku_col = 'SKU' if 'SKU' in products_df.columns else None
    if sku_col:
        skus = products_df[sku_col].dropna().astype(str).str.strip().unique().tolist()
        return [s for s in skus if s and s != '']
    return []

def get_skus_for_method(method):
    """Get list of SKUs available for the selected decoration method, sorted A-Z"""
    if products_df.empty:
        return []
    
    valid_skus = []
    for _, row in products_df.iterrows():
        sku = str(row.get('SKU', '')).strip()
        if not sku:
            continue
        
        is_valid, _ = is_sku_valid_for_method(sku, method)
        if is_valid:
            valid_skus.append(sku)
    
    # Sort SKUs alphabetically
    return sorted(valid_skus)

def get_colors_for_sku(sku):
    """Get available colors for a SKU (comma-separated)"""
    if products_df.empty or not sku:
        return []
    sku_clean = str(sku).strip()
    matches = products_df[products_df['SKU'].astype(str).str.strip() == sku_clean]
    if not matches.empty:
        colors_str = matches.iloc[0].get('Colors', '')
        if pd.notna(colors_str) and str(colors_str).strip() != '':
            # Parse colors (comma-separated)
            colors = [c.strip() for c in str(colors_str).split(',')]
            return [c for c in colors if c]
    return []

def get_sku_details(sku):
    """Get Brand and Description for a SKU using column positions (A=SKU, B=Brand, C=Description)"""
    if products_df.empty:
        return '', ''
    sku_clean = str(sku).strip()
    # Try to match by column name first (SKU column)
    sku_col_name = None
    if 'SKU' in products_df.columns:
        sku_col_name = 'SKU'
    elif len(products_df.columns) > 0:
        # If no 'SKU' column, use first column (column A)
        sku_col_name = products_df.columns[0]
    
    if sku_col_name:
        matches = products_df[products_df[sku_col_name].astype(str).str.strip() == sku_clean]
        if not matches.empty:
            row = matches.iloc[0]
            # Get Brand from column B (index 1)
            # Get Description from column C (index 2)
            if 'Brand' in products_df.columns and 'Description' in products_df.columns:
                # Use column names if available
                brand = row.get('Brand', '')
                description = row.get('Description', '')
            else:
                # Use positional indexing (column B = index 1, column C = index 2)
                brand = row.iloc[1] if len(row) > 1 else ''
                description = row.iloc[2] if len(row) > 2 else ''
            return str(brand), str(description)
    return '', ''

def get_valid_sizes(sku):
    """Get valid sizes for a SKU from Products sheet"""
    if products_df.empty:
        return []
    sku_clean = str(sku).strip()
    matches = products_df[products_df['SKU'].astype(str).str.strip() == sku_clean]
    if not matches.empty:
        sizes_str = matches.iloc[0].get('Sizes', '')
        if pd.notna(sizes_str) and sizes_str != '':
            # Parse sizes (assuming format like "XS, S, M, L, XL" or "XS,S,M,L,XL")
            sizes = [s.strip() for s in str(sizes_str).split(',')]
            return sizes
    return []  # Return empty list if no sizes found

def is_sku_valid_for_method(sku, method):
    """Gatekeeper validation: Check if SKU is valid for the selected decoration method"""
    if products_df.empty or not sku:
        return True, ''  # Allow if no products data or empty SKU
    
    sku_clean = str(sku).strip()
    matches = products_df[products_df['SKU'].astype(str).str.strip() == sku_clean]
    if matches.empty:
        return True, ''  # Allow if SKU not found (will be validated elsewhere)
    
    row = matches.iloc[0]
    
    # Check method-specific columns
    if method == 'Screenprint':
        sp_36 = row.get('SP 36', 0)
        sp_72 = row.get('SP 72', 0)
        try:
            sp_36_val = float(sp_36) if pd.notna(sp_36) and str(sp_36) != '' else 0
            sp_72_val = float(sp_72) if pd.notna(sp_72) and str(sp_72) != '' else 0
            if sp_36_val > 0 or sp_72_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Screenprint (SP 36 and SP 72 are 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Screenprint (SP 36 and SP 72 are 0 or missing)"
    
    elif method == 'Embroidery':
        emb_36 = row.get('EMB 36', 0)
        emb_72 = row.get('EMB 72', 0)
        try:
            emb_36_val = float(emb_36) if pd.notna(emb_36) and str(emb_36) != '' else 0
            emb_72_val = float(emb_72) if pd.notna(emb_72) and str(emb_72) != '' else 0
            if emb_36_val > 0 or emb_72_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Embroidery (EMB 36 and EMB 72 are 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Embroidery (EMB 36 and EMB 72 are 0 or missing)"
    
    elif method == 'Applique':
        app_36 = row.get('APP 36', 0)
        try:
            app_36_val = float(app_36) if pd.notna(app_36) and str(app_36) != '' else 0
            if app_36_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Applique (APP 36 is 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Applique (APP 36 is 0 or missing)"
    
    elif method == 'Sublimated Patches':
        sub_50 = row.get('SUB 50', 0)
        try:
            sub_50_val = float(sub_50) if pd.notna(sub_50) and str(sub_50) != '' else 0
            if sub_50_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Sublimated Patches (SUB 50 is 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Sublimated Patches (SUB 50 is 0 or missing)"
    
    elif method == 'Leather Patches':
        lth_50 = row.get('LTH 50', 0)
        try:
            lth_50_val = float(lth_50) if pd.notna(lth_50) and str(lth_50) != '' else 0
            if lth_50_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Leather Patches (LTH 50 is 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Leather Patches (LTH 50 is 0 or missing)"
    
    # If method not in the list, allow it
    return True, ''

def get_customer_address(customer_name):
    """Get address details for a customer"""
    if customers_df.empty:
        return '', '', '', '', ''
    customer_clean = str(customer_name).strip()
    # Try CompanyName first (actual column name), fallback to Customer
    customer_col = 'CompanyName' if 'CompanyName' in customers_df.columns else 'Customer'
    matches = customers_df[customers_df[customer_col].astype(str).str.strip() == customer_clean]
    if not matches.empty:
        row = matches.iloc[0]
        # Get address fields - return empty string if NaN/empty, don't convert to 'nan' string
        addr1 = '' if pd.isna(row.get('Address1', '')) or str(row.get('Address1', '')).strip() == '' else str(row.get('Address1', '')).strip()
        addr2 = '' if pd.isna(row.get('Address2', '')) or str(row.get('Address2', '')).strip() == '' else str(row.get('Address2', '')).strip()
        city = '' if pd.isna(row.get('AddressCity', '')) or str(row.get('AddressCity', '')).strip() == '' else str(row.get('AddressCity', '')).strip()
        state = '' if pd.isna(row.get('AddressState', '')) or str(row.get('AddressState', '')).strip() == '' else str(row.get('AddressState', '')).strip()
        zip_code_raw = row.get('AddressZip', '')
        if pd.isna(zip_code_raw) or str(zip_code_raw).strip() == '':
            zip_code = ''
        else:
            # Convert to string and remove decimal if it's a float (e.g., 12345.0 -> 12345)
            zip_str = str(zip_code_raw).strip()
            if '.' in zip_str:
                zip_code = zip_str.split('.')[0]
            else:
                zip_code = zip_str
        return addr1, addr2, city, state, zip_code
    return '', '', '', '', ''

def get_rep_by_url(url_identifier):
    """Find actual rep name from SalesReps sheet using URL identifier"""
    if salesreps_df.empty or not url_identifier:
        return None
    
    url_clean = str(url_identifier).strip().lower()
    
    # Look for URL column (case-insensitive check for column names)
    url_col = None
    for col in salesreps_df.columns:
        if str(col).strip().lower() in ['url', 'uniqueurl', 'unique_url', 'url_identifier']:
            url_col = col
            break
    
    if url_col and 'SalesRep' in salesreps_df.columns:
        # Match URL identifier to URL column
        matches = salesreps_df[salesreps_df[url_col].astype(str).str.strip().str.lower() == url_clean]
        if not matches.empty:
            return str(matches.iloc[0]['SalesRep']).strip()
    
    return None

def get_rep_pin(rep_name):
    """Get PIN for a given sales rep from SalesReps sheet"""
    if salesreps_df.empty or not rep_name:
        return None
    
    rep_clean = str(rep_name).strip()
    if 'SalesRep' in salesreps_df.columns:
        matches = salesreps_df[salesreps_df['SalesRep'].astype(str).str.strip() == rep_clean]
        if not matches.empty and 'PIN' in matches.columns:
            pin_value = matches.iloc[0]['PIN']
            # Return PIN as string, handling NaN/empty values
            if pd.notna(pin_value) and str(pin_value).strip() != '':
                return str(pin_value).strip()
    return None

def can_rep_view_sheets(rep_name):
    """Check if sales rep can view the Google Sheets link"""
    if salesreps_df.empty or not rep_name:
        return False
    
    rep_clean = str(rep_name).strip()
    if 'SalesRep' in salesreps_df.columns:
        matches = salesreps_df[salesreps_df['SalesRep'].astype(str).str.strip() == rep_clean]
        if not matches.empty:
            # Look for column that controls sheet visibility (case-insensitive)
            for col in salesreps_df.columns:
                col_lower = str(col).strip().lower()
                if col_lower in ['showsheets', 'show_sheets', 'canviewsheets', 'can_view_sheets', 'sheetsaccess', 'sheets_access']:
                    value = matches.iloc[0][col]
                    # Check if value is True, 'Yes', 'Y', '1', etc.
                    if pd.notna(value):
                        value_str = str(value).strip().lower()
                        if value_str in ['true', 'yes', 'y', '1', 'show']:
                            return True
    return False

def save_order_to_sheet(order_data, status='Draft', submission_number=''):
    """Save order to session state (for persistence - can be extended to Google Sheets API)"""
    if 'saved_orders' not in st.session_state:
        st.session_state.saved_orders = []
    
    # Convert dates to strings for JSON serialization
    order_data_copy = {}
    for key, value in order_data.items():
        if isinstance(value, dict):
            order_data_copy[key] = {}
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (date, datetime)):
                    order_data_copy[key][sub_key] = sub_value.isoformat() if sub_value else None
                else:
                    order_data_copy[key][sub_key] = sub_value
        else:
            order_data_copy[key] = value
    
    order_record = {
        'OrderID': str(uuid.uuid4())[:8],
        'SalesRep': order_data['header'].get('sales_rep', ''),
        'Status': status,  # 'Draft' or 'Submitted'
        'SubmissionNumber': submission_number,
        'PONumber': order_data['header'].get('po_number', ''),
        'Customer': order_data['header'].get('customer', ''),
        'OrderDate': str(order_data['header'].get('order_date', '')),
        'ShipDate': str(order_data['header'].get('ship_date', '')),
        'CreatedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'OrderData': json.dumps(order_data_copy, default=str)  # Store as JSON string
    }
    
    st.session_state.saved_orders.append(order_record)
    return order_record['OrderID']

def get_orders_for_rep(rep_name, status_filter=None):
    """Get orders for a specific rep from saved orders"""
    if 'saved_orders' not in st.session_state:
        return []
    
    rep_clean = str(rep_name).strip()
    orders = [o for o in st.session_state.saved_orders if str(o.get('SalesRep', '')).strip() == rep_clean]
    
    if status_filter:
        orders = [o for o in orders if o.get('Status', '') == status_filter]
    
    # Sort by created date (newest first)
    orders.sort(key=lambda x: x.get('CreatedDate', ''), reverse=True)
    return orders

def load_order_by_id(order_id):
    """Load order data by OrderID and restore date objects"""
    if 'saved_orders' not in st.session_state:
        return None
    
    for order in st.session_state.saved_orders:
        if order.get('OrderID') == order_id:
            try:
                # Parse order data from JSON string
                order_data = json.loads(order.get('OrderData', '{}'))
                
                # Restore date objects from ISO format strings
                if 'header' in order_data:
                    for date_field in ['order_date', 'ship_date', 'drop_dead_date']:
                        if date_field in order_data['header'] and order_data['header'][date_field]:
                            date_str = order_data['header'][date_field]
                            try:
                                # Try parsing ISO format date string
                                if isinstance(date_str, str):
                                    if 'T' in date_str:
                                        order_data['header'][date_field] = datetime.fromisoformat(date_str.split('T')[0]).date()
                                    else:
                                        order_data['header'][date_field] = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except (ValueError, AttributeError):
                                pass
                
                return {
                    'order_record': order,
                    'order_data': order_data
                }
            except Exception as e:
                return {
                    'order_record': order,
                    'order_data': None
                }
    
    return None

def get_customers_for_rep(sales_rep):
    """Get list of customers assigned to a sales rep, sorted A-Z"""
    if customers_df.empty or sales_rep is None:
        return []
    
    rep_clean = str(sales_rep).strip()
    customers_list = []
    
    # Filter customers directly from Customers sheet by SalesRep column
    if 'SalesRep' in customers_df.columns:
        customer_col = 'CompanyName' if 'CompanyName' in customers_df.columns else 'Customer'
        rep_customers = customers_df[customers_df['SalesRep'].astype(str).str.strip() == rep_clean][customer_col].unique().tolist()
        customers_list = [str(c).strip() for c in rep_customers if pd.notna(c) and str(c).strip()]
    # Fallback: if no SalesRep column, try SalesReps sheet
    elif not salesreps_df.empty and 'SalesRep' in salesreps_df.columns:
        customer_col = 'CompanyName' if 'CompanyName' in customers_df.columns else 'Customer'
        rep_customers = salesreps_df[salesreps_df['SalesRep'].astype(str).str.strip() == rep_clean]['Customer'].tolist()
        customers_list = [str(c).strip() for c in rep_customers if pd.notna(c)]
    # Final fallback: return all customers
    else:
        customer_col = 'CompanyName' if 'CompanyName' in customers_df.columns else 'Customer'
        if customer_col in customers_df.columns:
            customers_list = customers_df[customer_col].unique().tolist()
            customers_list = [str(c).strip() for c in customers_list if pd.notna(c) and str(c).strip()]
    
    # Sort A-Z
    return sorted(customers_list)

def calculate_row_total(row_dict):
    """Calculate total quantity for a row (dict format)"""
    size_cols = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
    total = 0
    for col in size_cols:
        try:
            val = row_dict.get(col, 0)
            if val and val != '':
                total += int(float(val))
        except (ValueError, TypeError):
            pass
    return total

def calculate_pricing_tier(total_units, method):
    """Determine pricing tier based on total units and decoration method"""
    if method == 'Screenprint' or method == 'Embroidery':
        if total_units >= 72:
            return '72pc'
        else:
            return '36pc'
    elif method == 'Applique':
        return '36pc'  # Only one tier
    elif method == 'Sublimated Patches' or method == 'Leather Patches':
        return '50pc'  # Only one tier
    else:
        return '36pc'  # Default fallback

def get_base_price(sku, method, pricing_tier):
    """Get base price for a SKU based on decoration method and pricing tier"""
    if products_df.empty or not sku:
        return 0.0
    
    sku_clean = str(sku).strip()
    matches = products_df[products_df['SKU'].astype(str).str.strip() == sku_clean]
    if matches.empty:
        return 0.0
    
    row = matches.iloc[0]
    
    # Determine which price column to use based on method and tier
    price_col = None
    if method == 'Screenprint':
        price_col = 'SP 72' if pricing_tier == '72pc' else 'SP 36'
    elif method == 'Embroidery':
        price_col = 'EMB 72' if pricing_tier == '72pc' else 'EMB 36'
    elif method == 'Applique':
        price_col = 'APP 36'
    elif method == 'Sublimated Patches':
        price_col = 'SUB 50'
    elif method == 'Leather Patches':
        price_col = 'LTH 50'
    
    if price_col and price_col in row:
        try:
            price = row.get(price_col, 0)
            price_val = float(price) if pd.notna(price) and str(price) != '' else 0.0
            return price_val
        except (ValueError, TypeError):
            return 0.0
    
    return 0.0

def get_size_upcharge(size):
    """Get upcharge for extended sizes"""
    size_upcharges = {
        'XS': 0.0,
        'S': 0.0,
        'M': 0.0,
        'L': 0.0,
        'XL': 0.0,
        '2XL': 3.0,
        '3XL': 4.0,
        '4XL': 5.0
    }
    return size_upcharges.get(size, 0.0)

def calculate_product_pricing(grid_list, method, pricing_tier, total_units):
    """Calculate total product pricing based on grid, method, tier, and options"""
    if not grid_list or total_units == 0:
        return 0.0
    
    # Get decoration options
    has_second_design = st.session_state.order_data['decoration']['has_second_design'] and method == 'Screenprint'
    confetti = st.session_state.order_data['decoration']['confetti'] and method == 'Embroidery'
    premium_4color = st.session_state.order_data['decoration']['premium_4color'] and method == 'Screenprint'
    design2_premium = st.session_state.order_data['decoration']['design2_premium_4color'] and has_second_design
    
    # Calculate per-unit upcharges
    per_unit_upcharge = 0.0
    if confetti:
        per_unit_upcharge += 2.0
    if premium_4color:
        per_unit_upcharge += 2.0  # Design 1 Premium 4-Color
    if has_second_design:
        per_unit_upcharge += 3.50
    if design2_premium:
        per_unit_upcharge += 2.0  # Design 2 Premium 4-Color (adds $4 total if both selected)
    
    total_product_price = 0.0
    size_cols = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
    
    for row in grid_list:
        sku = row.get('SKU', '').strip()
        if not sku:
            continue
        
        base_price = get_base_price(sku, method, pricing_tier)
        if base_price == 0.0:
            continue
        
        # Calculate price for each size in this row
        for size in size_cols:
            qty = row.get(size, 0)
            try:
                qty_val = int(float(qty)) if qty else 0
                if qty_val > 0:
                    size_upcharge = get_size_upcharge(size)
                    price_per_piece = base_price + size_upcharge + per_unit_upcharge
                    total_product_price += price_per_piece * qty_val
            except (ValueError, TypeError):
                pass
    
    return total_product_price

# Initialize authentication state
if 'authenticated_rep' not in st.session_state:
    st.session_state.authenticated_rep = None

# Get query parameters
query_params = st.query_params
is_admin = query_params.get('admin', 'false').lower() == 'true'
admin_pin = query_params.get('pin', '')

# Check for admin access FIRST (before rep check)
ADMIN_PIN = "ADMIN123"  # TODO: Move to Streamlit secrets for production

if is_admin:
    # Check admin PIN
    if admin_pin != ADMIN_PIN:
        st.error("❌ **Invalid Admin PIN.** Access denied.")
        st.info("💡 **How to access:** Add `?admin=true&pin=ADMIN123` to your URL")
        st.stop()
    
    # Admin authenticated - show log viewer and stop (don't need rep)
    st.title("📊 Activity Log Viewer")
    st.info("💡 **Note:** No SalesRep entry needed. Admin access is separate from sales rep authentication.")
    st.markdown("---")
    
    # Load logs from session state (in production, load from Google Sheets)
    if 'pending_logs' in st.session_state and st.session_state.pending_logs:
        logs_df = pd.DataFrame(st.session_state.pending_logs)
        
        # Filter for last 30 days
        logs_df['Timestamp'] = pd.to_datetime(logs_df['Timestamp'])
        thirty_days_ago = datetime.now() - pd.Timedelta(days=30)
        logs_df = logs_df[logs_df['Timestamp'] >= thirty_days_ago]
        
        # Sort by timestamp (newest first)
        logs_df = logs_df.sort_values('Timestamp', ascending=False)
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_rep = st.selectbox("Filter by Rep", options=['All'] + sorted(logs_df['Rep Name'].unique().tolist()))
        with col2:
            filter_event = st.selectbox("Filter by Event Type", options=['All'] + sorted(logs_df['Event Type'].unique().tolist()))
        with col3:
            filter_status = st.selectbox("Filter by Status", options=['All'] + sorted(logs_df['Status'].unique().tolist()))
        
        # Apply filters
        filtered_logs = logs_df.copy()
        if filter_rep != 'All':
            filtered_logs = filtered_logs[filtered_logs['Rep Name'] == filter_rep]
        if filter_event != 'All':
            filtered_logs = filtered_logs[filtered_logs['Event Type'] == filter_event]
        if filter_status != 'All':
            filtered_logs = filtered_logs[filtered_logs['Status'] == filter_status]
        
        # Display logs
        st.markdown(f"**Showing {len(filtered_logs)} log entries (last 30 days)**")
        
        # Highlight suspicious activity
        def highlight_suspicious(row):
            if row['Event Type'] == 'SUSPICIOUS_ACCESS' or (row['Event Type'] == 'PIN_ATTEMPT' and row['Status'] == 'Failure'):
                return ['background-color: #ffcccc'] * len(row)
            elif row['Event Type'] == 'LOGIN_SUCCESS':
                return ['background-color: #ccffcc'] * len(row)
            return [''] * len(row)
        
        if not filtered_logs.empty:
            styled_logs = filtered_logs.style.apply(highlight_suspicious, axis=1)
            st.dataframe(styled_logs, use_container_width=True, hide_index=True)
            
            # Export to CSV
            csv_logs = filtered_logs.to_csv(index=False)
            st.download_button(
                label="📥 Export Logs to CSV",
                data=csv_logs,
                file_name=f"activity_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No logs found matching the selected filters.")
    else:
        st.info("No logs available. Logs will appear here as activity occurs.")
    
    st.markdown("---")
    st.markdown("**Note:** Logs are currently stored in session state. For production, configure Google Sheets API to persist logs.")
    st.stop()  # Stop here - admin doesn't need to access the main app

# Get rep from URL query parameter (only if not admin)
url_identifier = query_params.get('rep', None)

# If no rep in URL, show error and stop
if not url_identifier:
    st.error("⚠️ **Access Denied**\n\nPlease access this portal using your unique sales rep URL (e.g., `?rep=yourname`).")
    st.stop()

# Convert URL identifier to actual rep name from sheet
actual_rep_name = get_rep_by_url(url_identifier)

# Check if rep exists
if actual_rep_name is None:
    # Log suspicious access attempt
    log_event("SUSPICIOUS_ACCESS", "Failure", f"Invalid URL identifier: {url_identifier}")
    st.error(f"⚠️ **Sales Rep not found.**\n\nPlease verify your URL is correct or contact your administrator.")
    st.stop()

# Check if this rep is already authenticated
# If URL rep changes, require re-authentication
if st.session_state.authenticated_rep != actual_rep_name:
    # Log authentication screen display
    log_event("AUTH_SCREEN", "Info", f"Authentication screen shown for {actual_rep_name}")
    
    # Not authenticated yet or rep changed - show PIN entry screen
    st.title("🔐 Sales Rep Authentication")
    st.markdown(f"**Sales Rep:** {actual_rep_name}")
    
    # PIN input
    pin_input = st.text_input("Enter your PIN:", type="password", key='pin_input')
    
    if st.button("Authenticate", key='auth_button'):
        # Get expected PIN for this rep
        expected_pin = get_rep_pin(actual_rep_name)
        
        if expected_pin is None:
            log_event("PIN_ATTEMPT", "Failure", f"PIN not configured for {actual_rep_name}")
            st.error("⚠️ **PIN not configured for this sales rep.**\n\nPlease contact your administrator.")
        elif pin_input.strip() == expected_pin:
            # PIN is correct - authenticate
            log_event("PIN_ATTEMPT", "Success", f"Correct PIN entered for {actual_rep_name}")
            log_event("LOGIN_SUCCESS", "Success", f"User authenticated as {actual_rep_name}")
            st.session_state.authenticated_rep = actual_rep_name
            st.session_state.order_data['header']['sales_rep'] = actual_rep_name
            # Clear customer selection when switching reps
            st.session_state.order_data['header']['customer'] = None
            st.rerun()
        else:
            log_event("PIN_ATTEMPT", "Failure", f"Incorrect PIN entered for {actual_rep_name}")
            st.error("❌ **Incorrect PIN.** Please try again.")
    
    st.stop()  # Stop here until authenticated

# Authentication successful - proceed with app
# Set the sales rep in order data
st.session_state.authenticated_rep = st.session_state.authenticated_rep  # Ensure it's set
st.session_state.order_data['header']['sales_rep'] = st.session_state.authenticated_rep

# Check for admin log viewer access
query_params = st.query_params
is_admin = query_params.get('admin', 'false').lower() == 'true'
admin_pin = query_params.get('pin', '')

# Admin PIN (hardcoded - no need for SalesRep sheet entry)
# To access admin logs, add to URL: ?admin=true&pin=ADMIN123
# Example: https://yourapp.streamlit.app?admin=true&pin=ADMIN123
ADMIN_PIN = "ADMIN123"  # TODO: Move to Streamlit secrets for production

if is_admin:
    # Check admin PIN
    if admin_pin != ADMIN_PIN:
        st.error("❌ **Invalid Admin PIN.** Access denied.")
        st.info("💡 **How to access:** Add `?admin=true&pin=ADMIN123` to your URL")
        st.stop()
    # Show admin log viewer
    st.title("📊 Activity Log Viewer")
    st.markdown("---")
    
    # Load logs from session state (in production, load from Google Sheets)
    if 'pending_logs' in st.session_state and st.session_state.pending_logs:
        logs_df = pd.DataFrame(st.session_state.pending_logs)
        
        # Filter for last 30 days
        logs_df['Timestamp'] = pd.to_datetime(logs_df['Timestamp'])
        thirty_days_ago = datetime.now() - pd.Timedelta(days=30)
        logs_df = logs_df[logs_df['Timestamp'] >= thirty_days_ago]
        
        # Sort by timestamp (newest first)
        logs_df = logs_df.sort_values('Timestamp', ascending=False)
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_rep = st.selectbox("Filter by Rep", options=['All'] + sorted(logs_df['Rep Name'].unique().tolist()))
        with col2:
            filter_event = st.selectbox("Filter by Event Type", options=['All'] + sorted(logs_df['Event Type'].unique().tolist()))
        with col3:
            filter_status = st.selectbox("Filter by Status", options=['All'] + sorted(logs_df['Status'].unique().tolist()))
        
        # Apply filters
        filtered_logs = logs_df.copy()
        if filter_rep != 'All':
            filtered_logs = filtered_logs[filtered_logs['Rep Name'] == filter_rep]
        if filter_event != 'All':
            filtered_logs = filtered_logs[filtered_logs['Event Type'] == filter_event]
        if filter_status != 'All':
            filtered_logs = filtered_logs[filtered_logs['Status'] == filter_status]
        
        # Display logs
        st.markdown(f"**Showing {len(filtered_logs)} log entries (last 30 days)**")
        
        # Highlight suspicious activity
        def highlight_suspicious(row):
            if row['Event Type'] == 'SUSPICIOUS_ACCESS' or (row['Event Type'] == 'PIN_ATTEMPT' and row['Status'] == 'Failure'):
                return ['background-color: #ffcccc'] * len(row)
            elif row['Event Type'] == 'LOGIN_SUCCESS':
                return ['background-color: #ccffcc'] * len(row)
            return [''] * len(row)
        
        if not filtered_logs.empty:
            styled_logs = filtered_logs.style.apply(highlight_suspicious, axis=1)
            st.dataframe(styled_logs, use_container_width=True, hide_index=True)
            
            # Export to CSV
            csv_logs = filtered_logs.to_csv(index=False)
            st.download_button(
                label="📥 Export Logs to CSV",
                data=csv_logs,
                file_name=f"activity_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No logs found matching the selected filters.")
    else:
        st.info("No logs available. Logs will appear here as activity occurs.")
    
    st.markdown("---")
    st.markdown("**Note:** Logs are currently stored in session state. For production, configure Google Sheets API to persist logs.")

# Main App Title with Navigation buttons on the right
authenticated_rep_name = st.session_state.authenticated_rep

col_title, col_nav = st.columns([3, 1])
with col_title:
    st.title("👕 Eagle Resort Wear Portal 🦅")

with col_nav:
    # Navigation buttons
    if st.button("📋 My Orders", key='nav_my_orders', use_container_width=True):
        st.session_state.view_mode = 'my_orders'
        st.session_state.show_order_review = False
        st.session_state.order_submitted = False
        st.rerun()
    
    # Conditionally show Google Sheets link based on rep permissions
    if authenticated_rep_name and can_rep_view_sheets(authenticated_rep_name):
        SHEETS_LINK = "https://docs.google.com/spreadsheets/d/14DYELQWKuQefjFEpTaltaS5YHhXeiIhr-QJ327mGwt0/edit?usp=sharing"
        st.markdown(f"📊 [View/Edit Data Sheets]({SHEETS_LINK})")

st.markdown("---")

# My Orders View
if st.session_state.view_mode == 'my_orders':
    st.header("📋 My Orders")
    
    # Get orders for this rep
    all_orders = get_orders_for_rep(authenticated_rep_name)
    submitted_orders = [o for o in all_orders if o.get('Status') == 'Submitted']
    draft_orders = [o for o in all_orders if o.get('Status') == 'Draft']
    
    # Tabs for Submitted and Drafts
    tab1, tab2 = st.tabs([f"✅ Submitted ({len(submitted_orders)})", f"💾 Drafts ({len(draft_orders)})"])
    
    with tab1:
        if submitted_orders:
            st.markdown("### Submitted Orders")
            for order in submitted_orders:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.write(f"**PO#:** {order.get('PONumber', 'N/A')} | **Customer:** {order.get('Customer', 'N/A')}")
                        st.write(f"**Submission #:** {order.get('SubmissionNumber', 'N/A')} | **Order Date:** {order.get('OrderDate', 'N/A')}")
                    with col2:
                        st.write(f"**Created:** {order.get('CreatedDate', 'N/A')}")
                    with col3:
                        if st.button("👁️ View", key=f"view_submitted_{order.get('OrderID')}"):
                            st.session_state.viewing_order_id = order.get('OrderID')
                            st.session_state.view_mode = 'view_order'
                            st.rerun()
                    st.markdown("---")
        else:
            st.info("No submitted orders yet.")
    
    with tab2:
        if draft_orders:
            st.markdown("### Draft Orders")
            for order in draft_orders:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        po_num = order.get('PONumber', 'N/A')
                        if po_num == '' or po_num == 'N/A':
                            po_num = 'No PO#'
                        st.write(f"**PO#:** {po_num} | **Customer:** {order.get('Customer', 'N/A')}")
                        st.write(f"**Created:** {order.get('CreatedDate', 'N/A')}")
                    with col2:
                        st.write(f"**Last Saved:** {order.get('CreatedDate', 'N/A')}")
                    with col3:
                        if st.button("✏️ Edit", key=f"edit_draft_{order.get('OrderID')}"):
                            st.session_state.viewing_order_id = order.get('OrderID')
                            st.session_state.view_mode = 'edit_order'
                            st.rerun()
                    st.markdown("---")
        else:
            st.info("No draft orders saved.")
    
    st.markdown("---")
    if st.button("← Back to New Order", key='back_to_new'):
        st.session_state.view_mode = 'new_order'
        st.rerun()
    
    st.stop()  # Stop here - don't show the order form

# View/Edit Order Mode
if st.session_state.view_mode in ['view_order', 'edit_order']:
    viewing_order_id = st.session_state.get('viewing_order_id')
    if viewing_order_id:
        loaded_order = load_order_by_id(viewing_order_id)
        if loaded_order and loaded_order.get('order_record'):
            order_record = loaded_order['order_record']
            order_data = loaded_order.get('order_data')
            
            st.header(f"{'👁️ View Order' if st.session_state.view_mode == 'view_order' else '✏️ Edit Order'}")
            st.write(f"**PO#:** {order_record.get('PONumber', 'N/A')} | **Customer:** {order_record.get('Customer', 'N/A')}")
            st.write(f"**Status:** {order_record.get('Status', 'N/A')} | **Submission #:** {order_record.get('SubmissionNumber', 'N/A')}")
            st.write(f"**Created:** {order_record.get('CreatedDate', 'N/A')}")
            
            if order_data and st.session_state.view_mode == 'edit_order':
                # Load order data into session state for editing
                # Restore date objects from ISO format strings
                if 'header' in order_data:
                    for date_field in ['order_date', 'ship_date', 'drop_dead_date']:
                        if date_field in order_data['header'] and order_data['header'][date_field]:
                            date_val = order_data['header'][date_field]
                            if isinstance(date_val, str):
                                try:
                                    if 'T' in date_val:
                                        order_data['header'][date_field] = datetime.fromisoformat(date_val.split('T')[0]).date()
                                    else:
                                        order_data['header'][date_field] = datetime.strptime(date_val, '%Y-%m-%d').date()
                                except (ValueError, AttributeError):
                                    pass
                
                st.session_state.order_data = order_data
                st.success("✅ Order loaded. You can now edit it below.")
                st.session_state.view_mode = 'new_order'
                if 'viewing_order_id' in st.session_state:
                    del st.session_state.viewing_order_id
                st.rerun()
            elif order_data and st.session_state.view_mode == 'view_order':
                # Display order in read-only view (similar to review screen)
                st.markdown("---")
                with st.expander("📦 Order Information", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Sales Rep:** {order_data['header'].get('sales_rep', 'N/A')}")
                        st.write(f"**Customer:** {order_data['header'].get('customer', 'N/A')}")
                        st.write(f"**PO#:** {order_data['header'].get('po_number', 'N/A')}")
                        st.write(f"**Tax Status:** {order_data['header'].get('tax_status', 'N/A')}")
                        st.write(f"**Tags:** {order_data['header'].get('tags', 'N/A')}")
                        st.write(f"**Delivery Method:** {order_data['header'].get('delivery_method', 'N/A')}")
                    with col2:
                        order_date = order_data['header'].get('order_date')
                        ship_date = order_data['header'].get('ship_date')
                        drop_dead_date = order_data['header'].get('drop_dead_date')
                        st.write(f"**Order Date:** {order_date if order_date else 'N/A'}")
                        st.write(f"**Ship Date:** {ship_date if ship_date else 'N/A'}")
                        st.write(f"**Drop Dead Date:** {drop_dead_date if drop_dead_date else 'N/A'}")
                
                with st.expander("📍 Shipping Address"):
                    st.write(f"**Address 1:** {order_data['header'].get('shipping_address1', 'N/A')}")
                    addr2 = order_data['header'].get('shipping_address2', '')
                    if addr2:
                        st.write(f"**Address 2:** {addr2}")
                    st.write(f"**City:** {order_data['header'].get('shipping_city', 'N/A')}")
                    st.write(f"**State:** {order_data['header'].get('shipping_state', 'N/A')}")
                    st.write(f"**Zip:** {order_data['header'].get('shipping_zip', 'N/A')}")
                
                with st.expander("🎨 Design Information"):
                    design_type = order_data['decoration'].get('design_type', 'New Design')
                    st.write(f"**Design Type:** {design_type}")
                    if design_type == 'New Design':
                        st.write(f"**Decoration Method:** {order_data['decoration'].get('method', 'N/A')}")
                        st.write(f"**Design 1 Number:** {order_data['decoration'].get('design1_number', 'N/A')}")
                        st.write(f"**Design 1 Details:** {order_data['decoration'].get('design1_description', 'N/A')}")
                
                with st.expander("👕 Products"):
                    grid = order_data.get('grid', [])
                    if grid:
                        product_summary = []
                        for row in grid:
                            sku = row.get('SKU', '').strip()
                            if sku:
                                qty_total = sum([
                                    int(float(row.get(size, 0) or 0)) 
                                    for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
                                ])
                                if qty_total > 0:
                                    sizes_list = []
                                    for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']:
                                        qty = int(float(row.get(size, 0) or 0))
                                        if qty > 0:
                                            sizes_list.append(f"{size}: {qty}")
                                    product_summary.append({
                                        'SKU': sku,
                                        'Brand': row.get('Brand', ''),
                                        'Description': row.get('Description', ''),
                                        'Color': row.get('Color', ''),
                                        'Sizes': ', '.join(sizes_list),
                                        'Total Qty': qty_total
                                    })
                        if product_summary:
                            df_products = pd.DataFrame(product_summary)
                            st.dataframe(df_products, use_container_width=True, hide_index=True)
            
            if st.button("← Back to My Orders", key='back_to_orders'):
                st.session_state.view_mode = 'my_orders'
                if 'viewing_order_id' in st.session_state:
                    del st.session_state.viewing_order_id
                st.rerun()
            
            st.stop()
        else:
            st.error("Order not found.")
            st.session_state.view_mode = 'my_orders'
            st.rerun()

# Save Draft button (always visible when in new order mode)
if st.session_state.view_mode == 'new_order' and not st.session_state.show_order_review and not st.session_state.order_submitted:
    col_save, col_spacer = st.columns([1, 5])
    with col_save:
        if st.button("💾 Save Draft", key='save_draft'):
            # Save current order as draft
            import json
            order_data_copy = json.loads(json.dumps(st.session_state.order_data, default=str))
            order_id = save_order_to_sheet(order_data_copy, status='Draft')
            st.success(f"✅ Draft saved! (ID: {order_id})")
            st.info("💡 You can access your drafts from the 'My Orders' section.")

# ORDER SECTION
st.header("Order")

# Sales Rep and Customer (side by side)
col_rep, col_cust = st.columns(2)

with col_rep:
    # Sales Rep is locked to authenticated rep - show as read-only
    authenticated_rep_name = st.session_state.authenticated_rep
    st.text_input(
        "Sales Rep",
        value=authenticated_rep_name,
        disabled=True,
        key='sales_rep_display'
    )
    # Keep sales_rep in session state
    st.session_state.order_data['header']['sales_rep'] = authenticated_rep_name

with col_cust:
    # Customer Dropdown (filtered by authenticated Sales Rep)
    # Use container to stabilize layout
    customer_container = st.container()
    with customer_container:
        # Always use authenticated rep for customer filtering
        available_customers = get_customers_for_rep(authenticated_rep_name)
        
        if available_customers:
            selected_customer = st.selectbox(
                "Customer",
                options=[''] + available_customers,
                index=0 if st.session_state.order_data['header']['customer'] is None else (available_customers.index(st.session_state.order_data['header']['customer']) + 1 if st.session_state.order_data['header']['customer'] in available_customers else 0),
                key='customer_select'
            )
        else:
            selected_customer = None
            # Use placeholder to maintain layout height
            st.selectbox("Customer", options=[''], disabled=True, key='customer_select_empty')
    
    # Auto-fill address when customer is selected
    if selected_customer:
        prev_customer = st.session_state.order_data['header'].get('customer')
        if selected_customer != prev_customer:
            # Customer changed, update address
            addr1, addr2, city, state, zip_code = get_customer_address(selected_customer)
            st.session_state.order_data['header']['shipping_address1'] = addr1
            st.session_state.order_data['header']['shipping_address2'] = addr2
            st.session_state.order_data['header']['shipping_city'] = city
            st.session_state.order_data['header']['shipping_state'] = state
            st.session_state.order_data['header']['shipping_zip'] = zip_code
        st.session_state.order_data['header']['customer'] = selected_customer
    else:
        st.session_state.order_data['header']['customer'] = None

# Row 1: Order Date, Ship Date, Drop Dead Date
col_date1, col_date2, col_date3 = st.columns(3)

with col_date1:
    order_date = st.date_input(
        "Order Date",
        value=st.session_state.order_data['header']['order_date'],
        key='order_date_input'
    )
    st.session_state.order_data['header']['order_date'] = order_date

with col_date2:
    order_date = st.session_state.order_data['header']['order_date']
    min_ship_date = order_date if order_date else date.today()
    ship_date = st.date_input(
        "Ship Date",
        value=st.session_state.order_data['header']['ship_date'],
        min_value=min_ship_date,
        key='ship_date_input',
        help="Must be on or after Order Date"
    )
    st.session_state.order_data['header']['ship_date'] = ship_date

with col_date3:
    order_date = st.session_state.order_data['header']['order_date']
    ship_date = st.session_state.order_data['header']['ship_date']
    # Use the later of order_date or ship_date as minimum
    if ship_date and order_date:
        min_drop_dead = ship_date if ship_date > order_date else order_date
    elif ship_date:
        min_drop_dead = ship_date
    elif order_date:
        min_drop_dead = order_date
    else:
        min_drop_dead = date.today()
    
    drop_dead_date = st.date_input(
        "Drop Dead Date",
        value=st.session_state.order_data['header']['drop_dead_date'],
        min_value=min_drop_dead,
        key='drop_dead_date_input',
        help="Must be on or after Ship Date"
    )
    st.session_state.order_data['header']['drop_dead_date'] = drop_dead_date

# Row 2: PO#, Tax Status, Tags, Delivery Method
col_po, col_tax, col_tags, col_delivery = st.columns(4)

with col_po:
    po_number = st.text_input(
        "PO#",
        value=st.session_state.order_data['header']['po_number'],
        key='po_number_input'
    )
    st.session_state.order_data['header']['po_number'] = po_number

with col_tax:
    tax_status = st.selectbox(
        "Tax Status",
        options=['Taxable', 'Exempt'],
        index=0 if st.session_state.order_data['header']['tax_status'] == 'Taxable' else 1,
        key='tax_status_select'
    )
    st.session_state.order_data['header']['tax_status'] = tax_status

with col_tags:
    tags = st.selectbox(
        "Tags",
        options=['Yes', 'No'],
        index=0 if st.session_state.order_data['header']['tags'] == 'Yes' else 1,
        key='tags_select'
    )
    st.session_state.order_data['header']['tags'] = tags

with col_delivery:
    # Initialize delivery_method if it doesn't exist (for existing sessions)
    if 'delivery_method' not in st.session_state.order_data['header']:
        st.session_state.order_data['header']['delivery_method'] = 'Standard Ground Shipping'
    
    delivery_method = st.selectbox(
        "Delivery Method",
        options=['Standard Ground Shipping', 'Sales Representative Delivery'],
        index=0 if st.session_state.order_data['header']['delivery_method'] == 'Standard Ground Shipping' else 1,
        key='delivery_method_select'
    )
    st.session_state.order_data['header']['delivery_method'] = delivery_method

# Notes Field
notes = st.text_area(
    "Order Notes",
    value=st.session_state.order_data['header']['notes'],
    key='notes_input',
    height=100,
    help="Order notes (supports line breaks from copy/paste)"
)
st.session_state.order_data['header']['notes'] = notes

# US States list
US_STATES = ['', 'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']

# Shipping Address
st.markdown("### Shipping Address")
shipping_addr1 = st.text_input("Address 1", value=st.session_state.order_data['header']['shipping_address1'])
shipping_addr2 = st.text_input("Address 2", value=st.session_state.order_data['header']['shipping_address2'])

col_ship1, col_ship2, col_ship3 = st.columns(3)
with col_ship1:
    shipping_city = st.text_input("City", value=st.session_state.order_data['header']['shipping_city'])
with col_ship2:
    current_state = st.session_state.order_data['header']['shipping_state']
    state_index = US_STATES.index(current_state) if current_state in US_STATES else 0
    shipping_state = st.selectbox("State", options=US_STATES, index=state_index)
with col_ship3:
    shipping_zip = st.text_input("Zip", value=st.session_state.order_data['header']['shipping_zip'])

st.session_state.order_data['header']['shipping_address1'] = shipping_addr1
st.session_state.order_data['header']['shipping_address2'] = shipping_addr2
st.session_state.order_data['header']['shipping_city'] = shipping_city
st.session_state.order_data['header']['shipping_state'] = shipping_state
st.session_state.order_data['header']['shipping_zip'] = shipping_zip

# Billing Address
st.markdown("### Billing Address")

# Same as Shipping checkbox - moved to be next to Billing Address
same_as_shipping = st.checkbox(
    "Same as Shipping Address",
    value=st.session_state.order_data['header']['same_as_shipping'],
    key='same_as_shipping_checkbox'
)
st.session_state.order_data['header']['same_as_shipping'] = same_as_shipping
if same_as_shipping:
    # Display shipping address values when "Same as Shipping" is checked
    st.text_input("Address 1", value=shipping_addr1, key='billing_addr1_display', disabled=True)
    st.text_input("Address 2", value=shipping_addr2, key='billing_addr2_display', disabled=True)
    col_bill1, col_bill2, col_bill3 = st.columns(3)
    with col_bill1:
        st.text_input("City", value=shipping_city, key='billing_city_display', disabled=True)
    with col_bill2:
        st.text_input("State", value=shipping_state, key='billing_state_display', disabled=True)
    with col_bill3:
        st.text_input("Zip", value=shipping_zip, key='billing_zip_display', disabled=True)
    
    # Update session state
    st.session_state.order_data['header']['billing_address1'] = shipping_addr1
    st.session_state.order_data['header']['billing_address2'] = shipping_addr2
    st.session_state.order_data['header']['billing_city'] = shipping_city
    st.session_state.order_data['header']['billing_state'] = shipping_state
    st.session_state.order_data['header']['billing_zip'] = shipping_zip
else:
    # Allow manual entry when unchecked
    billing_addr1 = st.text_input("Address 1", value=st.session_state.order_data['header']['billing_address1'], key='billing_addr1')
    billing_addr2 = st.text_input("Address 2", value=st.session_state.order_data['header']['billing_address2'], key='billing_addr2')
    col_bill1, col_bill2, col_bill3 = st.columns(3)
    with col_bill1:
        billing_city = st.text_input("City", value=st.session_state.order_data['header']['billing_city'], key='billing_city')
    with col_bill2:
        billing_state_current = st.session_state.order_data['header']['billing_state']
        billing_state_index = US_STATES.index(billing_state_current) if billing_state_current in US_STATES else 0
        billing_state = st.selectbox("State", options=US_STATES, index=billing_state_index, key='billing_state_select')
    with col_bill3:
        billing_zip = st.text_input("Zip", value=st.session_state.order_data['header']['billing_zip'], key='billing_zip')
    
    # Update session state
    st.session_state.order_data['header']['billing_address1'] = billing_addr1
    st.session_state.order_data['header']['billing_address2'] = billing_addr2
    st.session_state.order_data['header']['billing_city'] = billing_city
    st.session_state.order_data['header']['billing_state'] = billing_state
    st.session_state.order_data['header']['billing_zip'] = billing_zip

st.markdown("---")

# DESIGN SECTION
st.header("Design")

# Design Type Selection (New Design or Re-Order)
# Initialize design_type and reference_order_number if they don't exist (for existing sessions)
if 'design_type' not in st.session_state.order_data['decoration']:
    st.session_state.order_data['decoration']['design_type'] = 'New Design'
if 'reference_order_number' not in st.session_state.order_data['decoration']:
    st.session_state.order_data['decoration']['reference_order_number'] = ''

design_type = st.radio(
    "Design Type",
    options=['New Design', 'Re-Order'],
    index=0 if st.session_state.order_data['decoration']['design_type'] == 'New Design' else 1,
    key='design_type_radio',
    horizontal=True
)
st.session_state.order_data['decoration']['design_type'] = design_type

# Conditional display based on design type
if design_type == 'Re-Order':
    # Re-Order: Show only Reference Order Number and Design Details
    reference_order_number = st.text_input(
        "Reference Order Number",
        value=st.session_state.order_data['decoration'].get('reference_order_number', ''),
        key='reference_order_number'
    )
    st.session_state.order_data['decoration']['reference_order_number'] = reference_order_number
    
    design_details = st.text_area(
        "Design Details",
        value=st.session_state.order_data['decoration']['design1_description'],
        key='reorder_design_details',
        height=80
    )
    st.session_state.order_data['decoration']['design1_description'] = design_details
    
else:
    # New Design: Show all fields
    # Decoration Method Selection
    decoration_method = st.radio(
        "Decoration Method",
        options=['Screenprint', 'Embroidery', 'Applique', 'Sublimated Patches', 'Leather Patches'],
        index=['Screenprint', 'Embroidery', 'Applique', 'Sublimated Patches', 'Leather Patches'].index(st.session_state.order_data['decoration']['method']) if st.session_state.order_data['decoration']['method'] in ['Screenprint', 'Embroidery', 'Applique', 'Sublimated Patches', 'Leather Patches'] else 0,
        key='decoration_method_radio',
        horizontal=True
    )
    st.session_state.order_data['decoration']['method'] = decoration_method

    # Design 1
    st.markdown("### Design 1")
    col_design1a, col_design1b = st.columns(2)

    with col_design1a:
        design1_number_input = st.text_input("Design Number", value=st.session_state.order_data['decoration']['design1_number'], key='design1_number')
        # Validate numeric input (allowing decimals like 78542.02)
        if design1_number_input == '' or re.match(r'^[0-9]+(\.[0-9]+)?$', design1_number_input):
            design1_number = design1_number_input
            st.session_state.order_data['decoration']['design1_number'] = design1_number
        else:
            st.warning("Design Number must be numeric (decimals allowed, e.g., 78542.02)")
            design1_number = st.session_state.order_data['decoration']['design1_number']
        
        design1_location = st.text_input("Decoration Location", value=st.session_state.order_data['decoration']['design1_location'], key='design1_location')
        st.session_state.order_data['decoration']['design1_location'] = design1_location

    with col_design1b:
        pass  # Keep column structure but leave empty

    design1_description = st.text_area("Design Details", value=st.session_state.order_data['decoration']['design1_description'], key='design1_description', height=80)
    st.session_state.order_data['decoration']['design1_description'] = design1_description

    design1_colors = st.text_area("Requested Colors", value=st.session_state.order_data['decoration']['design1_colors'], key='design1_colors', height=60)
    
    # Update session state based on checkbox BEFORE processing colors
    design1_let_designers_pick = st.checkbox(
        "Let Designers Pick",
        value=st.session_state.order_data['decoration']['design1_let_designers_pick'],
        key='design1_let_designers_pick_checkbox'
    )
    st.session_state.order_data['decoration']['design1_let_designers_pick'] = design1_let_designers_pick
    
    if design1_let_designers_pick:
        st.session_state.order_data['decoration']['design1_colors'] = "Let designers pick colors"
    else:
        # Only update if it's currently set to "Let designers pick colors" (don't overwrite user input)
        if st.session_state.order_data['decoration']['design1_colors'] == "Let designers pick colors":
            st.session_state.order_data['decoration']['design1_colors'] = ""
        else:
            st.session_state.order_data['decoration']['design1_colors'] = design1_colors

    # Upcharge options for Design 1
    if decoration_method == 'Embroidery':
        confetti = st.checkbox("Confetti Thread (+$2.00/pc)", value=st.session_state.order_data['decoration']['confetti'], key='confetti_checkbox')
        st.session_state.order_data['decoration']['confetti'] = confetti
        st.session_state.order_data['decoration']['premium_4color'] = False
    elif decoration_method == 'Screenprint':
        premium_4color = st.checkbox("Premium 4-Color (+$2.00/pc)", value=st.session_state.order_data['decoration']['premium_4color'], key='premium_4color_checkbox')
        st.session_state.order_data['decoration']['premium_4color'] = premium_4color
        st.session_state.order_data['decoration']['confetti'] = False
    else:
        st.session_state.order_data['decoration']['confetti'] = False
        st.session_state.order_data['decoration']['premium_4color'] = False

    # Custom Art Charge (moved below checkboxes)
    art_setup_hours = st.number_input(
        "Custom Art Charge ($25 per half-hour)",
        min_value=0.0,
        step=0.5,
        value=st.session_state.order_data['decoration']['art_setup_hours'],
        key='art_setup_hours_input',
        help="Enter hours (0.5 = half-hour, 1.0 = 1 hour, etc.)"
    )
    st.session_state.order_data['decoration']['art_setup_hours'] = art_setup_hours

    # File Upload for Design Assets
    uploaded_file = st.file_uploader(
        "Upload Design Files (Images, PDFs, Vector Art)",
        type=['png', 'jpg', 'jpeg', 'pdf', 'svg', 'eps', 'ai'],
        key='design_file_upload',
        help="Supported formats: PNG, JPG, JPEG, PDF, SVG, EPS, AI"
    )
    if uploaded_file is not None:
        st.success(f"File uploaded: {uploaded_file.name} ({uploaded_file.size} bytes)")

    # Design 2 (only for Screenprint)
    if decoration_method == 'Screenprint':
        has_second_design = st.checkbox(
            "Add Second Design (+$3.50/pc)",
            value=st.session_state.order_data['decoration']['has_second_design'],
            key='has_second_design_checkbox'
        )
        st.session_state.order_data['decoration']['has_second_design'] = has_second_design
        
        if has_second_design:
            st.markdown("### Design 2")
            col_design2a, col_design2b = st.columns(2)
            
            with col_design2a:
                design2_number_input = st.text_input("Design Number", value=st.session_state.order_data['decoration']['design2_number'], key='design2_number')
                # Validate numeric input (allowing decimals like 78542.02)
                if design2_number_input == '' or re.match(r'^[0-9]+(\.[0-9]+)?$', design2_number_input):
                    design2_number = design2_number_input
                    st.session_state.order_data['decoration']['design2_number'] = design2_number
                else:
                    st.warning("Design Number must be numeric (decimals allowed, e.g., 78542.02)")
                    design2_number = st.session_state.order_data['decoration']['design2_number']
                
                design2_location = st.text_input("Decoration Location", value=st.session_state.order_data['decoration']['design2_location'], key='design2_location')
                st.session_state.order_data['decoration']['design2_location'] = design2_location
            
            design2_description = st.text_area("Design Details", value=st.session_state.order_data['decoration']['design2_description'], key='design2_description', height=80)
            st.session_state.order_data['decoration']['design2_description'] = design2_description
            
            design2_colors = st.text_area("Requested Colors", value=st.session_state.order_data['decoration']['design2_colors'], key='design2_colors', height=60)
            
            # Update session state based on checkbox BEFORE processing colors
            design2_let_designers_pick = st.checkbox(
                "Let Designers Pick",
                value=st.session_state.order_data['decoration']['design2_let_designers_pick'],
                key='design2_let_designers_pick_checkbox'
            )
            st.session_state.order_data['decoration']['design2_let_designers_pick'] = design2_let_designers_pick
            
            if design2_let_designers_pick:
                st.session_state.order_data['decoration']['design2_colors'] = "Let designers pick colors"
            else:
                # Only update if it's currently set to "Let designers pick colors" (don't overwrite user input)
                if st.session_state.order_data['decoration']['design2_colors'] == "Let designers pick colors":
                    st.session_state.order_data['decoration']['design2_colors'] = ""
                else:
                    st.session_state.order_data['decoration']['design2_colors'] = design2_colors
            
            design2_premium_4color = st.checkbox(
                "Premium 4-Color (+$2.00/pc)",
                value=st.session_state.order_data['decoration']['design2_premium_4color'],
                key='design2_premium_4color_checkbox'
            )
            st.session_state.order_data['decoration']['design2_premium_4color'] = design2_premium_4color
        else:
            st.session_state.order_data['decoration']['has_second_design'] = False

st.markdown("---")

# PRODUCT SECTION
st.header("Product")

# Initialize grid if empty
if not st.session_state.order_data['grid']:
    st.session_state.order_data['grid'] = [{
        'SKU': '',
        'Brand': '',
        'Description': '',
        'Color': '',
        'XS': 0, 'S': 0, 'M': 0, 'L': 0, 'XL': 0, '2XL': 0, '3XL': 0, '4XL': 0,
        'RowTotal': 0
    }]

# Get available SKUs filtered by decoration method
current_method = st.session_state.order_data['decoration']['method']
available_skus_for_method = get_skus_for_method(current_method)

# Product Grid - Dynamic Rows
size_cols = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']

# Handle delete row tracking in session state
if 'rows_to_delete' not in st.session_state:
    st.session_state.rows_to_delete = set()

# Get grid from session state
grid = st.session_state.order_data['grid']

# Check for add item button click from previous run
if 'add_item_clicked' in st.session_state and st.session_state.add_item_clicked:
    grid.append({
        'SKU': '',
        'Brand': '',
        'Description': '',
        'Color': '',
        'XS': 0, 'S': 0, 'M': 0, 'L': 0, 'XL': 0, '2XL': 0, '3XL': 0, '4XL': 0,
        'RowTotal': 0
    })
    st.session_state.add_item_clicked = False
    st.session_state.order_data['grid'] = grid  # Update session state

# Check for delete button clicks from previous run and remove rows
if st.session_state.rows_to_delete:
    grid = [row for idx, row in enumerate(grid) if idx not in st.session_state.rows_to_delete]
    st.session_state.rows_to_delete = set()

# Process each row and render widgets
new_grid = []
total_units = 0

for row_idx, row in enumerate(grid):
    with st.container():
        col_sku, col_brand, col_desc, col_color, col_delete = st.columns([2, 2, 3, 2, 1])
        
        with col_sku:
            # SKU Dropdown (filtered by decoration method)
            sku_options = [''] + available_skus_for_method
            current_sku = row.get('SKU', '')
            sku_index = sku_options.index(current_sku) if current_sku in sku_options else 0
            selected_sku = st.selectbox(
                "SKU",
                options=sku_options,
                index=sku_index,
                key=f'sku_select_{row_idx}'
            )
        
        # Auto-populate Brand and Description
        # THE KEY ISSUE: Streamlit widgets with keys maintain their own state.
        # The `value` parameter only sets the initial value. After that, Streamlit uses
        # the widget's internal state, NOT the `value` parameter.
        # SOLUTION: Include SKU in the widget key so when SKU changes, Streamlit
        # treats it as a new widget and uses the new `value`.
        stored_sku = row.get('SKU', '')
        if selected_sku:
            # Fetch brand/description for selected SKU
            brand, description = get_sku_details(selected_sku)
        else:
            # No SKU selected
            brand = row.get('Brand', '')
            description = row.get('Description', '')
        
        # Include SKU in widget key so Streamlit treats it as a new widget when SKU changes
        sku_for_key = selected_sku if selected_sku else f'empty_{row_idx}'
        with col_brand:
            brand_value = st.text_input("Brand", value=brand, key=f'brand_{row_idx}_{sku_for_key}', label_visibility="visible")
        
        with col_desc:
            desc_value = st.text_input("Description", value=description, key=f'desc_{row_idx}_{sku_for_key}', label_visibility="visible")
        
        with col_color:
            # Color Dropdown (filtered by SKU)
            color_options = [''] + get_colors_for_sku(selected_sku)
            current_color = row.get('Color', '')
            color_index = color_options.index(current_color) if current_color in color_options else 0
            selected_color = st.selectbox(
                "Color",
                options=color_options,
                index=color_index,
                key=f'color_select_{row_idx}'
            )
        
        with col_delete:
            if st.button("🗑️", key=f'delete_row_{row_idx}', help="Delete this row"):
                st.session_state.rows_to_delete.add(row_idx)
                st.rerun()
        
        # Size inputs
        valid_sizes = get_valid_sizes(selected_sku) if selected_sku else []
        size_inputs = {}
        
        # Create size columns
        size_cols_ui = st.columns(len(size_cols))
        for size_idx, size_col in enumerate(size_cols):
            with size_cols_ui[size_idx]:
                is_disabled = size_col not in valid_sizes if selected_sku else False
                current_qty = row.get(size_col, 0)
                size_inputs[size_col] = st.number_input(
                    size_col,
                    min_value=0,
                    step=1,
                    value=int(current_qty) if current_qty else 0,
                    key=f'{size_col}_{row_idx}',
                    disabled=is_disabled
                )
        
        # Calculate row total
        row_total = sum(size_inputs.values())
        total_units += row_total
        
        # Store row data
        new_row = {
            'SKU': selected_sku,
            'Brand': brand_value,
            'Description': desc_value,
            'Color': selected_color,
            **size_inputs,
            'RowTotal': row_total
        }
        new_grid.append(new_row)
        
        st.markdown("---")

# Add Item button (appears after all product rows)
if st.button("➕ Add Item", key='add_row_button'):
    st.session_state.order_data['grid'].append({
        'SKU': '',
        'Brand': '',
        'Description': '',
        'Color': '',
        'XS': 0, 'S': 0, 'M': 0, 'L': 0, 'XL': 0, '2XL': 0, '3XL': 0, '4XL': 0,
        'RowTotal': 0
    })
    st.rerun()

# Update session state
st.session_state.order_data['grid'] = new_grid

# Pricing Summary (always show)
st.markdown("### Pricing Summary")
current_method = st.session_state.order_data['decoration']['method']
if total_units > 0:
    pricing_tier = calculate_pricing_tier(total_units, current_method)
else:
    # Default tier based on method
    if current_method == 'Sublimated Patches' or current_method == 'Leather Patches':
        pricing_tier = '50pc'
    else:
        pricing_tier = '36pc'
st.write(f"**Total Units:** {int(total_units)}")
st.write(f"**Pricing Tier:** {pricing_tier}")

# Calculate product pricing
product_total = calculate_product_pricing(new_grid, current_method, pricing_tier, total_units)

# Calculate additional charges (these are already included in product pricing, but shown separately for clarity)
confetti_charge = 0.0
premium_4color_charge = 0.0
second_design_charge = 0.0
design2_premium_charge = 0.0

if st.session_state.order_data['decoration']['confetti'] and current_method == 'Embroidery':
    confetti_charge = 2.0 * total_units
if st.session_state.order_data['decoration']['premium_4color'] and current_method == 'Screenprint':
    premium_4color_charge = 2.0 * total_units
if current_method == 'Screenprint' and st.session_state.order_data['decoration']['has_second_design']:
    second_design_charge = 3.50 * total_units
    if st.session_state.order_data['decoration']['design2_premium_4color']:
        design2_premium_charge = 2.0 * total_units

art_setup_fee = st.session_state.order_data['decoration']['art_setup_hours'] * 50.0  # $25 per half-hour = $50 per hour

# Display pricing breakdown
if product_total > 0:
    st.write(f"**Product Total:** ${product_total:.2f}")
if confetti_charge > 0:
    st.write(f"**Confetti Thread:** ${confetti_charge:.2f}")
if premium_4color_charge > 0:
    st.write(f"**Premium 4-Color:** ${premium_4color_charge:.2f}")
if second_design_charge > 0:
    st.write(f"**Second Design:** ${second_design_charge:.2f}")
if design2_premium_charge > 0:
    st.write(f"**Design 2 Premium 4-Color:** ${design2_premium_charge:.2f}")
st.write(f"**Art Setup Fee:** ${art_setup_fee:.2f}")

# Calculate grand total
grand_total = product_total + art_setup_fee
st.write(f"**TOTAL:** ${grand_total:.2f}")

st.markdown("---")

# SHOPWORKS EXPORT SECTION
st.header("Export to ShopWorks OnSite")

def pivot_grid_to_line_items(grid_list):
    """Convert size matrix (wide) to line items (long format)"""
    if not grid_list:
        return pd.DataFrame()
    
    line_items = []
    size_cols_all = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
    size_index_map = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, '2XL': 5, '3XL': 6, '4XL': 7}
    
    for row in grid_list:
        sku = str(row.get('SKU', '')).strip()
        color = str(row.get('Color', '')).strip()
        
        if not sku:
            continue
        
        for size_col in size_cols_all:
            qty = row.get(size_col, 0)
            try:
                qty_val = int(float(qty)) if qty else 0
                if qty_val > 0:
                    line_items.append({
                        'CustomerID': st.session_state.order_data['header']['customer'] or '',
                        'ItemCode': sku,
                        'ColorCode': color,
                        'SizeIndex': size_index_map.get(size_col, 0),
                        'Size': size_col,
                        'Quantity': qty_val,
                        'Price': 0.0  # Price would need to be calculated from pricing tiers
                    })
            except (ValueError, TypeError):
                pass
    
    return pd.DataFrame(line_items)

# Validation function before submission
def validate_order_before_submission():
    """Validate order data before allowing submission"""
    errors = []
    warnings = []
    
    # Required fields
    if not st.session_state.order_data['header'].get('po_number', '').strip():
        errors.append("PO# is required")
    
    if not st.session_state.order_data['header'].get('customer'):
        errors.append("Customer is required")
    
    if not st.session_state.order_data['header'].get('shipping_address1', '').strip():
        errors.append("Shipping Address is required")
    
    if not st.session_state.order_data['header'].get('shipping_city', '').strip():
        errors.append("Shipping City is required")
    
    if not st.session_state.order_data['header'].get('shipping_state', '').strip():
        errors.append("Shipping State is required")
    
    if not st.session_state.order_data['header'].get('shipping_zip', '').strip():
        errors.append("Shipping Zip is required")
    
    # Check if there are any products
    grid = st.session_state.order_data['grid']
    has_products = False
    total_qty = 0
    for row in grid:
        if row.get('SKU', '').strip():
            has_products = True
            # Check if any quantities are entered
            for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']:
                try:
                    qty = int(float(row.get(size, 0) or 0))
                    total_qty += qty
                except (ValueError, TypeError):
                    pass
    
    if not has_products:
        errors.append("At least one product (SKU) must be added")
    elif total_qty == 0:
        errors.append("At least one quantity must be entered for products")
    
    # Check decoration method is selected (for New Design)
    if st.session_state.order_data['decoration']['design_type'] == 'New Design':
        if not st.session_state.order_data['decoration'].get('method'):
            errors.append("Decoration Method is required for New Design")
    
    # Date validation
    order_date = st.session_state.order_data['header'].get('order_date')
    ship_date = st.session_state.order_data['header'].get('ship_date')
    drop_dead_date = st.session_state.order_data['header'].get('drop_dead_date')
    
    if order_date and ship_date:
        if ship_date < order_date:
            errors.append("Ship Date must be on or after Order Date")
    
    if order_date and drop_dead_date:
        if drop_dead_date < order_date:
            errors.append("Drop Dead Date must be on or after Order Date")
    
    if ship_date and drop_dead_date:
        if drop_dead_date < ship_date:
            errors.append("Drop Dead Date must be on or after Ship Date")
    
    # Warnings (non-blocking)
    if not ship_date:
        warnings.append("Ship Date is not set")
    
    if not drop_dead_date:
        warnings.append("Drop Dead Date is not set")
    
    return errors, warnings

# Review state is already initialized at the top of the file

# Button to start review/submission process
if not st.session_state.show_order_review and not st.session_state.order_submitted:
    if st.button("📋 Review Order & Generate Export", type="primary"):
        # Validate before showing review
        errors, warnings = validate_order_before_submission()
        
        if errors:
            st.error("❌ **Cannot submit order. Please fix the following errors:**")
            for error in errors:
                st.error(f"  • {error}")
        elif warnings:
            st.warning("⚠️ **Warnings (order can still be submitted):**")
            for warning in warnings:
                st.warning(f"  • {warning}")
            # Show review even with warnings
            st.session_state.show_order_review = True
            st.rerun()
        else:
            # No errors or warnings - show review
            st.session_state.show_order_review = True
            st.rerun()

# Order Review Screen
if st.session_state.show_order_review and not st.session_state.order_submitted:
    st.markdown("---")
    st.header("📋 Order Review")
    st.markdown("Please review your order details before submitting:")
    
    # Order Information
    with st.expander("📦 Order Information", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Sales Rep:** {st.session_state.order_data['header'].get('sales_rep', 'N/A')}")
            st.write(f"**Customer:** {st.session_state.order_data['header'].get('customer', 'N/A')}")
            st.write(f"**PO#:** {st.session_state.order_data['header'].get('po_number', 'N/A')}")
            st.write(f"**Tax Status:** {st.session_state.order_data['header'].get('tax_status', 'N/A')}")
            st.write(f"**Tags:** {st.session_state.order_data['header'].get('tags', 'N/A')}")
            st.write(f"**Delivery Method:** {st.session_state.order_data['header'].get('delivery_method', 'N/A')}")
        
        with col2:
            order_date = st.session_state.order_data['header'].get('order_date')
            ship_date = st.session_state.order_data['header'].get('ship_date')
            drop_dead_date = st.session_state.order_data['header'].get('drop_dead_date')
            st.write(f"**Order Date:** {order_date.strftime('%Y-%m-%d') if order_date else 'N/A'}")
            st.write(f"**Ship Date:** {ship_date.strftime('%Y-%m-%d') if ship_date else 'N/A'}")
            st.write(f"**Drop Dead Date:** {drop_dead_date.strftime('%Y-%m-%d') if drop_dead_date else 'N/A'}")
        
        notes = st.session_state.order_data['header'].get('notes', '')
        if notes:
            st.write(f"**Notes:** {notes}")
    
    # Shipping Address
    with st.expander("📍 Shipping Address"):
        st.write(f"**Address 1:** {st.session_state.order_data['header'].get('shipping_address1', 'N/A')}")
        addr2 = st.session_state.order_data['header'].get('shipping_address2', '')
        if addr2:
            st.write(f"**Address 2:** {addr2}")
        st.write(f"**City:** {st.session_state.order_data['header'].get('shipping_city', 'N/A')}")
        st.write(f"**State:** {st.session_state.order_data['header'].get('shipping_state', 'N/A')}")
        st.write(f"**Zip:** {st.session_state.order_data['header'].get('shipping_zip', 'N/A')}")
        
        if st.session_state.order_data['header'].get('same_as_shipping', False):
            st.write("**Billing Address:** Same as Shipping Address")
        else:
            st.write("**Billing Address:**")
            st.write(f"  Address 1: {st.session_state.order_data['header'].get('billing_address1', 'N/A')}")
            addr2_bill = st.session_state.order_data['header'].get('billing_address2', '')
            if addr2_bill:
                st.write(f"  Address 2: {addr2_bill}")
            st.write(f"  City: {st.session_state.order_data['header'].get('billing_city', 'N/A')}")
            st.write(f"  State: {st.session_state.order_data['header'].get('billing_state', 'N/A')}")
            st.write(f"  Zip: {st.session_state.order_data['header'].get('billing_zip', 'N/A')}")
    
    # Design Information
    with st.expander("🎨 Design Information"):
        design_type = st.session_state.order_data['decoration'].get('design_type', 'New Design')
        st.write(f"**Design Type:** {design_type}")
        
        if design_type == 'Re-Order':
            st.write(f"**Reference Order Number:** {st.session_state.order_data['decoration'].get('reference_order_number', 'N/A')}")
            st.write(f"**Design Details:** {st.session_state.order_data['decoration'].get('design1_description', 'N/A')}")
        else:
            st.write(f"**Decoration Method:** {st.session_state.order_data['decoration'].get('method', 'N/A')}")
            st.write(f"**Design 1 Number:** {st.session_state.order_data['decoration'].get('design1_number', 'N/A')}")
            st.write(f"**Design 1 Location:** {st.session_state.order_data['decoration'].get('design1_location', 'N/A')}")
            st.write(f"**Design 1 Details:** {st.session_state.order_data['decoration'].get('design1_description', 'N/A')}")
            
            if st.session_state.order_data['decoration'].get('has_second_design', False):
                st.write(f"**Design 2 Number:** {st.session_state.order_data['decoration'].get('design2_number', 'N/A')}")
                st.write(f"**Design 2 Location:** {st.session_state.order_data['decoration'].get('design2_location', 'N/A')}")
                st.write(f"**Design 2 Details:** {st.session_state.order_data['decoration'].get('design2_description', 'N/A')}")
            
            art_hours = st.session_state.order_data['decoration'].get('art_setup_hours', 0)
            if art_hours > 0:
                st.write(f"**Custom Art Charge:** {art_hours} hours (${art_hours * 50:.2f})")
    
    # Products
    with st.expander("👕 Products"):
        grid = st.session_state.order_data['grid']
        if grid:
            product_summary = []
            for row in grid:
                sku = row.get('SKU', '').strip()
                if sku:
                    qty_total = sum([
                        int(float(row.get(size, 0) or 0)) 
                        for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
                    ])
                    if qty_total > 0:
                        sizes_list = []
                        for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']:
                            qty = int(float(row.get(size, 0) or 0))
                            if qty > 0:
                                sizes_list.append(f"{size}: {qty}")
                        product_summary.append({
                            'SKU': sku,
                            'Brand': row.get('Brand', ''),
                            'Description': row.get('Description', ''),
                            'Color': row.get('Color', ''),
                            'Sizes': ', '.join(sizes_list),
                            'Total Qty': qty_total
                        })
            
            if product_summary:
                df_products = pd.DataFrame(product_summary)
                st.dataframe(df_products, use_container_width=True, hide_index=True)
            else:
                st.write("No products with quantities entered.")
        else:
            st.write("No products added.")
    
    # Pricing Summary
    with st.expander("💰 Pricing Summary"):
        current_method = st.session_state.order_data['decoration']['method']
        total_units = sum([
            int(float(row.get(size, 0) or 0))
            for row in st.session_state.order_data['grid']
            for size in ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']
        ])
        
        if total_units > 0:
            pricing_tier = calculate_pricing_tier(total_units, current_method)
        else:
            if current_method == 'Sublimated Patches' or current_method == 'Leather Patches':
                pricing_tier = '50pc'
            else:
                pricing_tier = '36pc'
        
        product_total = calculate_product_pricing(st.session_state.order_data['grid'], current_method, pricing_tier, total_units)
        art_setup_fee = st.session_state.order_data['decoration']['art_setup_hours'] * 50.0
        grand_total = product_total + art_setup_fee
        
        st.write(f"**Total Units:** {int(total_units)}")
        st.write(f"**Pricing Tier:** {pricing_tier}")
        st.write(f"**Product Total:** ${product_total:.2f}")
        st.write(f"**Custom Art Charge:** ${art_setup_fee:.2f}")
        st.write(f"**TOTAL:** ${grand_total:.2f}")
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("✏️ Edit Order", key='edit_order'):
            st.session_state.show_order_review = False
            st.rerun()
    
    with col2:
        if st.button("✅ Confirm & Generate Export", type="primary", key='confirm_export'):
            export_df = pivot_grid_to_line_items(st.session_state.order_data['grid'])
            
            if not export_df.empty:
                # Generate submission number
                submission_number = generate_submission_number()
                
                # Save order to history
                save_order_to_sheet(st.session_state.order_data, status='Submitted', submission_number=submission_number)
                
                # Log order submission
                order_details = f"PO#: {st.session_state.order_data['header'].get('po_number', 'N/A')}, Customer: {st.session_state.order_data['header'].get('customer', 'N/A')}"
                log_event("ORDER_SUBMITTED", "Success", order_details, submission_number)
                
                # Convert to CSV
                csv_buffer = StringIO()
                export_df.to_csv(csv_buffer, index=False)
                csv_string = csv_buffer.getvalue()
                
                # Store CSV in session state for download
                st.session_state.export_csv = csv_string
                st.session_state.export_submission_number = submission_number
                st.session_state.export_line_count = len(export_df)
                st.session_state.show_order_review = False
                st.session_state.order_submitted = True
                st.rerun()
            else:
                st.warning("No line items to export. Please add items to the production grid.")
                st.session_state.show_order_review = False
                st.rerun()

# Show export success and download button after submission
if st.session_state.get('order_submitted', False):
    st.markdown("---")
    st.success(f"✅ **Order submitted successfully!** Submission Number: **{st.session_state.get('export_submission_number', 'N/A')}**")
    st.info(f"Export generated with {st.session_state.get('export_line_count', 0)} line items.")
    
    if 'export_csv' in st.session_state:
        st.download_button(
            label="📥 Download CSV Export",
            data=st.session_state.export_csv,
            file_name=f"shopworks_export_{st.session_state.export_submission_number}.csv",
            mime="text/csv",
            key='download_shopworks_csv',
            type="primary"
        )
        
        # Display preview
        export_df_preview = pd.read_csv(StringIO(st.session_state.export_csv))
        with st.expander("📄 Export Preview"):
            st.dataframe(export_df_preview, use_container_width=True)
    
    if st.button("🔄 Create New Order", key='new_order'):
        # Reset order data
        st.session_state.order_data = {
            'header': {
                'sales_rep': st.session_state.authenticated_rep,
                'customer': None,
                'order_date': date.today(),
                'ship_date': None,
                'drop_dead_date': None,
                'po_number': '',
                'tax_status': 'Taxable',
                'tags': 'No',
                'delivery_method': 'Standard Ground Shipping',
                'notes': '',
                'shipping_address1': '',
                'shipping_address2': '',
                'shipping_city': '',
                'shipping_state': '',
                'shipping_zip': '',
                'billing_address1': '',
                'billing_address2': '',
                'billing_city': '',
                'billing_state': '',
                'billing_zip': '',
                'same_as_shipping': False
            },
            'grid': [],
            'decoration': {
                'design_type': 'New Design',
                'reference_order_number': '',
                'method': 'Screenprint',
                'design1_number': '',
                'design1_location': '',
                'design1_description': '',
                'design1_colors': '',
                'design1_let_designers_pick': False,
                'design2_number': '',
                'design2_location': '',
                'design2_description': '',
                'design2_colors': '',
                'design2_let_designers_pick': False,
                'design2_premium_4color': False,
                'has_second_design': False,
                'confetti': False,
                'premium_4color': False,
                'art_setup_hours': 0.0
            }
        }
        st.session_state.show_order_review = False
        st.session_state.order_submitted = False
        if 'export_csv' in st.session_state:
            del st.session_state.export_csv
        if 'export_submission_number' in st.session_state:
            del st.session_state.export_submission_number
        if 'export_line_count' in st.session_state:
            del st.session_state.export_line_count
        st.rerun()

# Debug section (can be removed in production)
with st.expander("Debug: Session State"):
    st.json(st.session_state.order_data)
