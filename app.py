import streamlit as st
import pandas as pd
from db_functions import (
    connect_to_db,
    get_basic_info,
    get_additional_tables,
    get_categories,
    get_suppliers,
    add_new_manual_id,
    get_all_products,
    get_product_history,
    place_reorder,
    get_pending_reorders,
    mark_reorder_as_received
)

# Set page config
st.set_page_config(
    page_title="Inventory Management Dashboard",
    page_icon="📦",
    layout="wide"
)

# Sidebar
st.sidebar.title("📦 Inventory Management Dashboard")
option = st.sidebar.radio("Select Option:", ["Basic Information", "Operational Tasks"])

# Main space
st.title("🏭 Inventory and Supply Chain Dashboard")
st.markdown("---")

# Connect to BigQuery (no cursor needed for BigQuery)
try:
    client = connect_to_db()
    st.sidebar.success("✅ Connected to BigQuery")
except Exception as e:
    st.sidebar.error(f"❌ Connection failed: {e}")
    st.stop()

# --------------------- BASIC INFORMATION PAGE ---------------------
if option == "Basic Information":
    st.header("📊 Basic Metrics")
    
    # Get basic information from BigQuery
    with st.spinner("Loading dashboard metrics..."):
        basic_info = get_basic_info(client)
    
    # Display metrics in 2 rows of 3 columns
    cols = st.columns(3)
    keys = list(basic_info.keys())
    
    for i in range(3):
        with cols[i]:
            st.metric(label=keys[i], value=basic_info[keys[i]])
    
    cols = st.columns(3)
    for i in range(3, 6):
        with cols[i - 3]:
            st.metric(label=keys[i], value=basic_info[keys[i]])
    
    st.divider()
    
    # Fetch and display detailed tables
    st.header("📋 Detailed Information")
    with st.spinner("Loading detailed tables..."):
        tables = get_additional_tables(client)
    
    for label, data in tables.items():
        st.subheader(label)
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No data available")
        st.divider()

# --------------------- OPERATIONAL TASKS PAGE ---------------------
elif option == "Operational Tasks":
    st.header("⚙️ Operational Tasks")
    
    selected_task = st.selectbox(
        "Choose a Task",
        ["Add New Product", "Product History", "Place Reorder", "Receive Reorder"]
    )
    
    # ======================== ADD NEW PRODUCT ========================
    if selected_task == "Add New Product":
        st.header("➕ Add New Product")
        st.markdown("Fill in the details below to add a new product to inventory")
        
        with st.spinner("Loading categories and suppliers..."):
            categories = get_categories(client)
            suppliers = get_suppliers(client)
        
        with st.form("Add_Product_Form"):
            col1, col2 = st.columns(2)
            
            with col1:
                product_name = st.text_input("Product Name*", placeholder="Enter product name")
                product_category = st.selectbox("Category*", categories)
                product_price = st.number_input("Price (₹)*", min_value=0.0, step=0.01, format="%.2f")
            
            with col2:
                product_stock = st.number_input("Stock Quantity*", min_value=0, step=1)
                product_level = st.number_input("Reorder Level*", min_value=0, step=1)
                
                supplier_ids = [s["supplier_id"] for s in suppliers]
                supplier_names = [s["supplier_name"] for s in suppliers]
                
                supplier_id = st.selectbox(
                    "Supplier*",
                    options=supplier_ids,
                    format_func=lambda x: supplier_names[supplier_ids.index(x)]
                )
            
            st.markdown("*Required fields")
            submitted = st.form_submit_button("Add Product", use_container_width=True)
            
            if submitted:
                if not product_name:
                    st.error("⚠️ Please enter the product name.")
                elif product_price <= 0:
                    st.error("⚠️ Price must be greater than 0.")
                elif product_stock < 0:
                    st.error("⚠️ Stock quantity cannot be negative.")
                else:
                    try:
                        with st.spinner("Adding product..."):
                            add_new_manual_id(
                                client,
                                product_name,
                                product_category,
                                product_price,
                                product_stock,
                                product_level,
                                supplier_id
                            )
                        st.success(f"✅ Product '{product_name}' added successfully!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"❌ Error adding product: {e}")

    # ======================== PRODUCT HISTORY ========================
    elif selected_task == "Product History":
        st.header("📜 Product Inventory History")
        st.markdown("View complete history of shipments and stock changes")
        
        # Get product list
        with st.spinner("Loading products..."):
            products = get_all_products(client)
        
        if not products:
            st.warning("⚠️ No products found in the database")
        else:
            product_names = [p['product_name'] for p in products]
            product_ids = [p['product_id'] for p in products]
            
            selected_product_name = st.selectbox(
                "Select a Product",
                options=product_names,
                help="Choose a product to view its history"
            )
            
            if selected_product_name:
                selected_product_id = product_ids[product_names.index(selected_product_name)]
                
                with st.spinner(f"Loading history for {selected_product_name}..."):
                    history_data = get_product_history(client, selected_product_id)
                
                if history_data:
                    df = pd.DataFrame(history_data)
                    
                    # Display summary metrics
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Records", len(df))
                    
                    if 'change_type' in df.columns:
                        sales = len(df[df['change_type'] == 'Sale'])
                        restocks = len(df[df['change_type'] == 'Restock'])
                        col2.metric("Sales", sales)
                        col3.metric("Restocks", restocks)
                    
                    st.divider()
                    
                    # Display history table
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Download button
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download History as CSV",
                        data=csv,
                        file_name=f"{selected_product_name}_history.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("ℹ️ No history found for the selected product")

    # ======================== PLACE REORDER ========================
    elif selected_task == "Place Reorder":
        st.header("🛒 Place a Reorder")
        st.markdown("Create a new reorder request for low-stock products")
        
        with st.spinner("Loading products..."):
            products = get_all_products(client)
        
        if not products:
            st.warning("⚠️ No products available")
        else:
            product_names = [p['product_name'] for p in products]
            product_ids = [p['product_id'] for p in products]
            
            col1, col2 = st.columns(2)
            
            with col1:
                selected_product_name = st.selectbox(
                    "Select Product",
                    options=product_names,
                    help="Choose the product to reorder"
                )
            
            with col2:
                reorder_qty = st.number_input(
                    "Reorder Quantity",
                    min_value=1,
                    step=1,
                    help="Enter the quantity to reorder"
                )
            
            if st.button("🚀 Place Reorder", use_container_width=True):
                if not selected_product_name:
                    st.error("⚠️ Please select a product")
                elif reorder_qty <= 0:
                    st.error("⚠️ Reorder quantity must be greater than 0")
                else:
                    selected_product_id = product_ids[product_names.index(selected_product_name)]
                    try:
                        with st.spinner("Placing reorder..."):
                            place_reorder(client, selected_product_id, reorder_qty)
                        st.success(f"✅ Reorder placed for '{selected_product_name}' with quantity {reorder_qty}")
                        st.balloons()
                    except Exception as e:
                        st.error(f"❌ Error placing reorder: {e}")

    # ======================== RECEIVE REORDER ========================
    elif selected_task == "Receive Reorder":
        st.header("📦 Mark Reorder as Received")
        st.markdown("Update inventory when reorders arrive")
        
        # Fetch pending reorders
        with st.spinner("Loading pending reorders..."):
            pending_reorders = get_pending_reorders(client)
        
        if not pending_reorders:
            st.info("ℹ️ No pending reorders to receive")
            st.markdown("All reorders have been processed!")
        else:
            st.success(f"📋 Found {len(pending_reorders)} pending reorder(s)")
            
            reorder_ids = [r['reorder_id'] for r in pending_reorders]
            reorder_labels = [
                f"Reorder #{r['reorder_id']} - {r['product_name']}" 
                for r in pending_reorders
            ]
            
            selected_label = st.selectbox(
                "Select Reorder to Mark as Received",
                options=reorder_labels,
                help="Choose the reorder that has arrived"
            )
            
            if selected_label:
                selected_reorder_id = reorder_ids[reorder_labels.index(selected_label)]
                
                # Show confirmation
                st.info(f"📌 Selected: {selected_label}")
                
                col1, col2 = st.columns([3, 1])
                
                with col2:
                    if st.button("✅ Mark as Received", use_container_width=True, type="primary"):
                        try:
                            with st.spinner("Processing reorder..."):
                                mark_reorder_as_received(client, selected_reorder_id)
                            st.success(f"✅ Reorder #{selected_reorder_id} marked as received!")
                            st.success("✅ Inventory updated successfully!")
                            st.balloons()
                            
                            # Refresh the page after 2 seconds
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")

# Footer
st.divider()
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        <p>🏭 Inventory Management System | Powered by BigQuery | Made with ❤️ using Streamlit</p>
    </div>
    """,
    unsafe_allow_html=True
)
