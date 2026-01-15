import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
from datetime import date, datetime
import re

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
            'freight': 0.0,
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

# Ensure SalesReps has the expected structure if empty
if salesreps_df.empty:
    salesreps_df = pd.DataFrame(columns=['SalesRep', 'Customer'])

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
    
    elif method == 'Sublimation':
        sub_50 = row.get('SUB 50', 0)
        try:
            sub_50_val = float(sub_50) if pd.notna(sub_50) and str(sub_50) != '' else 0
            if sub_50_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Sublimation (SUB 50 is 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Sublimation (SUB 50 is 0 or missing)"
    
    elif method == 'Leather':
        lth_50 = row.get('LTH 50', 0)
        try:
            lth_50_val = float(lth_50) if pd.notna(lth_50) and str(lth_50) != '' else 0
            if lth_50_val > 0:
                return True, ''
            return False, f"SKU {sku} is not available for Leather (LTH 50 is 0 or missing)"
        except (ValueError, TypeError):
            return False, f"SKU {sku} is not available for Leather (LTH 50 is 0 or missing)"
    
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
        zip_code = '' if pd.isna(row.get('AddressZip', '')) or str(row.get('AddressZip', '')).strip() == '' else str(row.get('AddressZip', '')).strip()
        return addr1, addr2, city, state, zip_code
    return '', '', '', '', ''

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
    elif method == 'Sublimation' or method == 'Leather':
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
    elif method == 'Sublimation':
        price_col = 'SUB 50'
    elif method == 'Leather':
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

# Main App Title
st.title("👕 Eagle Resort Wear Portal 🦅")
# Link to Google Sheets
SHEETS_LINK = "https://docs.google.com/spreadsheets/d/14DYELQWKuQefjFEpTaltaS5YHhXeiIhr-QJ327mGwt0/edit?usp=sharing"
st.markdown(f"📊 [View/Edit Data Sheets]({SHEETS_LINK})")
st.markdown("---")

# ORDER SECTION
st.header("Order")

# Sales Rep and Customer (side by side)
col_rep, col_cust = st.columns(2)

with col_rep:
    # Sales Rep - Get list of existing sales reps
    if not salesreps_df.empty and 'SalesRep' in salesreps_df.columns:
        sales_reps = sorted(salesreps_df['SalesRep'].unique().tolist())
    else:
        # Fallback: extract from customers or use default
        sales_reps = sorted(customers_df['SalesRep'].unique().tolist()) if 'SalesRep' in customers_df.columns else ['Rep 1', 'Rep 2', 'Rep 3']
    
    # Initialize sales rep mode if not exists
    if 'sales_rep_mode' not in st.session_state:
        st.session_state.sales_rep_mode = 'select'
    
    # Sales Rep selection mode
    selected_rep = None
    if st.session_state.sales_rep_mode == 'select':
        rep_options = [''] + sales_reps + ['--- Add New ---']
        current_rep = st.session_state.order_data['header']['sales_rep'] or ''
        if current_rep in sales_reps:
            rep_index = sales_reps.index(current_rep) + 1
        else:
            rep_index = 0
        
        selected_rep_option = st.selectbox(
            "Sales Rep",
            options=rep_options,
            index=rep_index,
            key='sales_rep_select'
        )
        
        if selected_rep_option == '--- Add New ---':
            st.session_state.sales_rep_mode = 'new'
            st.session_state.order_data['header']['sales_rep'] = ''  # Clear current rep
            st.rerun()
        else:
            selected_rep = selected_rep_option if selected_rep_option else None
            # If switching from new mode back to existing rep, reset customer mode
            if selected_rep and selected_rep != current_rep:
                # Check if this rep has customers - if so, reset customer mode to select
                available_customers_check = get_customers_for_rep(selected_rep)
                if available_customers_check:
                    st.session_state.customer_mode = 'select'
    else:
        # New sales rep mode - text input
        new_rep = st.text_input(
            "Sales Rep (New)",
            value=st.session_state.order_data['header']['sales_rep'] or '',
            key='sales_rep_new_input'
        )
        selected_rep = new_rep.strip() if new_rep.strip() else None
        
        # Button to switch back to select mode
        if st.button("← Select from list", key='sales_rep_back'):
            st.session_state.sales_rep_mode = 'select'
            st.session_state.order_data['header']['sales_rep'] = None
            st.session_state.order_data['header']['customer'] = None
            st.session_state.customer_mode = 'select'
            st.rerun()
        
        # Add spacer to align with customer warning message
        st.markdown("<br>", unsafe_allow_html=True)
    
    # Update sales rep in session state
    st.session_state.order_data['header']['sales_rep'] = selected_rep if selected_rep else None

with col_cust:
    # Customer - Check if sales rep is new (not in list)
    current_rep = st.session_state.order_data['header']['sales_rep']
    is_new_rep = current_rep and current_rep not in sales_reps
    
    # Customer Dropdown (filtered by Sales Rep)
    customer_container = st.container()
    with customer_container:
        if current_rep and not is_new_rep:
            # Sales rep exists in list, get associated customers
            available_customers = get_customers_for_rep(current_rep)
        elif is_new_rep:
            # New sales rep - no customers available
            available_customers = []
        else:
            # No sales rep selected
            available_customers = []
        
        # Initialize customer mode if not exists
        if 'customer_mode' not in st.session_state:
            st.session_state.customer_mode = 'select'
        
        # Show message if new sales rep (aligned with customer field)
        if is_new_rep:
            st.info("ℹ️ No associated customers available for new sales rep.")
            # Force new mode for new rep
            st.session_state.customer_mode = 'new'
            new_customer = st.text_input(
                "Customer (New)",
                value=st.session_state.order_data['header']['customer'] or '',
                key='customer_new_input'
            )
            selected_customer = new_customer.strip() if new_customer.strip() else None
        elif available_customers:
            # If we have available customers and we're in new mode, switch to select mode
            # (This handles the case when switching from new sales rep back to existing one)
            if st.session_state.customer_mode == 'new' and not is_new_rep:
                st.session_state.customer_mode = 'select'
            
            # Customer selection mode
            if st.session_state.customer_mode == 'select':
                customer_options = [''] + available_customers + ['--- Add New ---']
                current_customer = st.session_state.order_data['header']['customer'] or ''
                if current_customer in available_customers:
                    cust_index = available_customers.index(current_customer) + 1
                else:
                    cust_index = 0
                
                selected_customer_option = st.selectbox(
                    "Customer",
                    options=customer_options,
                    index=cust_index,
                    key='customer_select'
                )
                
                if selected_customer_option == '--- Add New ---':
                    st.session_state.customer_mode = 'new'
                    st.session_state.order_data['header']['customer'] = ''  # Clear current customer
                    st.rerun()
                else:
                    selected_customer = selected_customer_option if selected_customer_option else None
            else:
                # New customer mode - text input
                new_customer = st.text_input(
                    "Customer (New)",
                    value=st.session_state.order_data['header']['customer'] or '',
                    key='customer_new_input'
                )
                selected_customer = new_customer.strip() if new_customer.strip() else None
                
                # Button to switch back to select mode
                if st.button("← Select from list", key='customer_back'):
                    st.session_state.customer_mode = 'select'
                    st.session_state.order_data['header']['customer'] = None
                    st.rerun()
        else:
            # No customers available (no sales rep selected) - show text input for new customer
            if st.session_state.customer_mode == 'select':
                st.session_state.customer_mode = 'new'
            
            new_customer = st.text_input(
                "Customer (New)",
                value=st.session_state.order_data['header']['customer'] or '',
                key='customer_new_input'
            )
            selected_customer = new_customer.strip() if new_customer.strip() else None
    
    # Auto-fill address when customer is selected (only if customer exists in list)
    if selected_customer:
        prev_customer = st.session_state.order_data['header'].get('customer')
        is_new_customer = selected_customer not in available_customers
        
        if selected_customer != prev_customer:
            if is_new_customer:
                # New customer - clear address fields
                st.session_state.order_data['header']['shipping_address1'] = ''
                st.session_state.order_data['header']['shipping_address2'] = ''
                st.session_state.order_data['header']['shipping_city'] = ''
                st.session_state.order_data['header']['shipping_state'] = ''
                st.session_state.order_data['header']['shipping_zip'] = ''
            else:
                # Existing customer - update address
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
    ship_date = st.date_input(
        "Ship Date",
        value=st.session_state.order_data['header']['ship_date'],
        key='ship_date_input'
    )
    st.session_state.order_data['header']['ship_date'] = ship_date

with col_date3:
    drop_dead_date = st.date_input(
        "Drop Dead Date",
        value=st.session_state.order_data['header']['drop_dead_date'],
        key='drop_dead_date_input'
    )
    st.session_state.order_data['header']['drop_dead_date'] = drop_dead_date

# Row 2: PO#, Tax Status, Tags, Freight
col_po, col_tax, col_tags, col_freight = st.columns(4)

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

with col_freight:
    freight = st.number_input(
        "Freight ($)",
        min_value=0.0,
        step=0.01,
        value=st.session_state.order_data['header']['freight'],
        key='freight_input'
    )
    st.session_state.order_data['header']['freight'] = freight

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

# Same as Shipping checkbox
same_as_shipping = st.checkbox(
    "Same as Shipping Address",
    value=st.session_state.order_data['header']['same_as_shipping'],
    key='same_as_shipping_checkbox'
)
st.session_state.order_data['header']['same_as_shipping'] = same_as_shipping

# Billing Address
st.markdown("### Billing Address")
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
        options=['Screenprint', 'Embroidery', 'Applique', 'Sublimation', 'Leather'],
        index=['Screenprint', 'Embroidery', 'Applique', 'Sublimation', 'Leather'].index(st.session_state.order_data['decoration']['method']) if st.session_state.order_data['decoration']['method'] in ['Screenprint', 'Embroidery', 'Applique', 'Sublimation', 'Leather'] else 0,
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

    design1_let_designers_pick = st.checkbox(
        "Let Designers Pick",
        value=st.session_state.order_data['decoration']['design1_let_designers_pick'],
        key='design1_let_designers_pick_checkbox'
    )
    st.session_state.order_data['decoration']['design1_let_designers_pick'] = design1_let_designers_pick

    # Update session state based on checkbox BEFORE rendering text_area
    if design1_let_designers_pick:
        st.session_state.order_data['decoration']['design1_colors'] = "Let designers pick colors"
    else:
        # Only update if it's currently set to "Let designers pick colors" (don't overwrite user input)
        if st.session_state.order_data['decoration']['design1_colors'] == "Let designers pick colors":
            st.session_state.order_data['decoration']['design1_colors'] = ""

    design1_colors = st.text_area("Requested Colors", value=st.session_state.order_data['decoration']['design1_colors'], key='design1_colors', height=60)
    if not design1_let_designers_pick:
        st.session_state.order_data['decoration']['design1_colors'] = design1_colors

    # Upcharge options for Design 1
    if decoration_method == 'Embroidery':
        confetti = st.checkbox("Confetti (+$2.00/pc)", value=st.session_state.order_data['decoration']['confetti'], key='confetti_checkbox')
        st.session_state.order_data['decoration']['confetti'] = confetti
        st.session_state.order_data['decoration']['premium_4color'] = False
    elif decoration_method == 'Screenprint':
        premium_4color = st.checkbox("Premium 4-Color (+$2.00/pc)", value=st.session_state.order_data['decoration']['premium_4color'], key='premium_4color_checkbox')
        st.session_state.order_data['decoration']['premium_4color'] = premium_4color
        st.session_state.order_data['decoration']['confetti'] = False
    else:
        st.session_state.order_data['decoration']['confetti'] = False
        st.session_state.order_data['decoration']['premium_4color'] = False

    # Art Setup Hours (moved below checkboxes)
    art_setup_hours = st.number_input(
        "Art Setup Hours ($25 per half-hour)",
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
            
            design2_let_designers_pick = st.checkbox(
                "Let Designers Pick",
                value=st.session_state.order_data['decoration']['design2_let_designers_pick'],
                key='design2_let_designers_pick_checkbox'
            )
            st.session_state.order_data['decoration']['design2_let_designers_pick'] = design2_let_designers_pick
            
            # Update session state based on checkbox BEFORE rendering text_area
            if design2_let_designers_pick:
                st.session_state.order_data['decoration']['design2_colors'] = "Let designers pick colors"
            else:
                # Only update if it's currently set to "Let designers pick colors" (don't overwrite user input)
                if st.session_state.order_data['decoration']['design2_colors'] == "Let designers pick colors":
                    st.session_state.order_data['decoration']['design2_colors'] = ""
            
            design2_colors = st.text_area("Requested Colors", value=st.session_state.order_data['decoration']['design2_colors'], key='design2_colors', height=60)
            if not design2_let_designers_pick:
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
    if current_method == 'Sublimation' or current_method == 'Leather':
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

if st.button("Generate ShopWorks Export", type="primary"):
    export_df = pivot_grid_to_line_items(st.session_state.order_data['grid'])
    
    if not export_df.empty:
        # Convert to CSV
        csv_buffer = StringIO()
        export_df.to_csv(csv_buffer, index=False)
        csv_string = csv_buffer.getvalue()
        
        st.success(f"Export generated with {len(export_df)} line items!")
        st.download_button(
            label="Download CSV",
            data=csv_string,
            file_name=f"shopworks_export_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key='download_shopworks_csv'
        )
        
        # Display preview
        st.markdown("### Export Preview")
        st.dataframe(export_df, use_container_width=True)
    else:
        st.warning("No line items to export. Please add items to the production grid.")

# Debug section (can be removed in production)
with st.expander("Debug: Session State"):
    st.json(st.session_state.order_data)
