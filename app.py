import streamlit as st
import pymysql
import pandas as pd
from datetime import datetime, timedelta
import config

st.set_page_config(page_title="仓库管理系统", page_icon="📦", layout="wide")

def get_db_connection():
    """
    创建数据库连接
    兼容 MySQL 8.0+ 和 TiDB
    """
    connection_params = {
        'host': config.DB_CONFIG['host'],
        'port': config.DB_CONFIG.get('port', 3306),
        'user': config.DB_CONFIG['user'],
        'password': config.DB_CONFIG['password'],
        'database': config.DB_CONFIG['database'],
        'charset': config.DB_CONFIG['charset'],
        'cursorclass': pymysql.cursors.DictCursor,
        'read_timeout': 30,
        'write_timeout': 30,
        'connect_timeout': 30
    }
    
    # TiDB 可能需要 SSL 连接
    if 'ssl_disabled' in config.DB_CONFIG and not config.DB_CONFIG['ssl_disabled']:
        connection_params['ssl'] = {
            'ca': '/etc/ssl/cert.pem'  # 默认 CA 证书路径
        }
    
    return pymysql.connect(**connection_params)

def init_connection():
    if 'db_connected' not in st.session_state:
        st.session_state.db_connected = False
    if not st.session_state.db_connected:
        try:
            conn = get_db_connection()
            conn.close()
            st.session_state.db_connected = True
        except Exception as e:
            st.error(f"数据库连接失败: {e}")
            st.warning("请确保MySQL已启动，并检查数据库配置")

def execute_query(query, params=None, fetch=True):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch:
                result = cursor.fetchall()
            else:
                conn.commit()
                result = cursor.lastrowid
        conn.close()
        return result
    except Exception as e:
        st.error(f"查询错误: {e}")
        return None

def update_inventory(warehouse_id, goods_id, quantity_change, is_inbound=True):
    """
    更新库存，当库存<=0时自动删除记录
    :param warehouse_id: 仓库ID
    :param goods_id: 货物ID
    :param quantity_change: 数量变化（正数）
    :param is_inbound: True表示入库，False表示出库
    """
    # 查找库存记录
    existing = execute_query("""
        SELECT * FROM inventory WHERE warehouse_id=%s AND goods_id=%s
    """, (warehouse_id, goods_id))
    
    if is_inbound:
        if existing:
            # 入库：更新现有库存
            execute_query("""
                UPDATE inventory 
                SET quantity = quantity + %s, actual_quantity = actual_quantity + %s, last_in_time = NOW()
                WHERE warehouse_id=%s AND goods_id=%s
            """, (quantity_change, quantity_change, warehouse_id, goods_id), fetch=False)
        else:
            # 入库：新增库存记录
            execute_query("""
                INSERT INTO inventory (warehouse_id, goods_id, quantity, actual_quantity, last_in_time)
                VALUES (%s, %s, %s, %s, NOW())
            """, (warehouse_id, goods_id, quantity_change, quantity_change), fetch=False)
    else:
        if existing:
            # 出库：更新现有库存
            execute_query("""
                UPDATE inventory 
                SET quantity = quantity - %s, actual_quantity = actual_quantity - %s, last_out_time = NOW()
                WHERE warehouse_id=%s AND goods_id=%s
            """, (quantity_change, quantity_change, warehouse_id, goods_id), fetch=False)
            
            # 检查库存是否<=0，如果是则删除
            inventory_after = execute_query("""
                SELECT quantity FROM inventory WHERE warehouse_id=%s AND goods_id=%s
            """, (warehouse_id, goods_id))
            
            if inventory_after and inventory_after[0]['quantity'] <= 0:
                execute_query("""
                    DELETE FROM inventory WHERE warehouse_id=%s AND goods_id=%s
                """, (warehouse_id, goods_id), fetch=False)

def main():
    init_connection()
    
    st.title("📦 仓库管理系统")
    
    st.sidebar.title("功能导航")
    page = st.sidebar.radio(
        "选择功能模块",
        ["首页", "仓库管理", "货物管理", "入库管理", "出库管理", "库存盘点", "库龄分析", "统计报表"]
    )
    
    if page == "首页":
        show_home()
    elif page == "仓库管理":
        show_warehouse_management()
    elif page == "货物管理":
        show_goods_management()
    elif page == "入库管理":
        show_inbound_management()
    elif page == "出库管理":
        show_outbound_management()
    elif page == "库存盘点":
        show_inventory_check()
    elif page == "库龄分析":
        show_age_analysis()
    elif page == "统计报表":
        show_statistics()

def show_home():
    st.header("系统概览")
    
    col1, col2, col3, col4 = st.columns(4)
    
    warehouse_count = execute_query("SELECT COUNT(*) as count FROM warehouses")
    goods_count = execute_query("SELECT COUNT(*) as count FROM goods")
    inventory_count = execute_query("SELECT SUM(quantity) as total FROM inventory")
    inbound_count = execute_query("SELECT COUNT(*) as count FROM inbound_records WHERE DATE(created_at) = CURDATE()")
    
    with col1:
        st.metric("仓库数量", warehouse_count[0]['count'] if warehouse_count else 0)
    with col2:
        st.metric("货物种类", goods_count[0]['count'] if goods_count else 0)
    with col3:
        st.metric("总库存量", inventory_count[0]['total'] if inventory_count and inventory_count[0]['total'] else 0)
    with col4:
        st.metric("今日入库", inbound_count[0]['count'] if inbound_count else 0)
    
    st.subheader("最近入库记录")
    recent_inbound = execute_query("""
        SELECT i.inbound_id, w.warehouse_name, g.goods_name, i.quantity, i.inbound_date, i.operator
        FROM inbound_records i
        JOIN warehouses w ON i.warehouse_id = w.warehouse_id
        JOIN goods g ON i.goods_id = g.goods_id
        ORDER BY i.inbound_date DESC
        LIMIT 10
    """)
    if recent_inbound:
        df_inbound = pd.DataFrame(recent_inbound)
        df_inbound = df_inbound.rename(columns={
            'inbound_id': '入库ID',
            'warehouse_name': '仓库名称',
            'goods_name': '货物名称',
            'quantity': '入库数量',
            'inbound_date': '入库时间',
            'operator': '操作人'
        })
        st.dataframe(df_inbound, use_container_width=True)

def show_warehouse_management():
    st.header("📦 仓库管理")
    
    # 添加新仓库表单
    with st.expander("➕ 添加新仓库", expanded=False):
        with st.form("add_warehouse_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input("仓库名称 *")
            with col2:
                location = st.text_input("仓库位置")
            with col3:
                manager = st.text_input("负责人")
            
            col4, col5 = st.columns(2)
            with col4:
                phone = st.text_input("联系电话")
            with col5:
                capacity = st.number_input("仓库容量", min_value=0, value=0)
            
            if st.form_submit_button("添加仓库", use_container_width=True, type="primary"):
                if name:
                    execute_query("""
                        INSERT INTO warehouses (warehouse_name, location, manager, phone, capacity)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (name, location, manager, phone, capacity), fetch=False)
                    st.success("✅ 仓库添加成功！")
                    st.rerun()
                else:
                    st.error("❌ 请填写仓库名称")
    
    st.subheader("仓库列表")
    warehouse_name_keyword = st.text_input("按仓库名称筛选", value="")
    if warehouse_name_keyword.strip():
        warehouses = execute_query(
            "SELECT * FROM warehouses WHERE warehouse_name LIKE %s ORDER BY warehouse_id",
            (f"%{warehouse_name_keyword.strip()}%",),
        )
    else:
        warehouses = execute_query("SELECT * FROM warehouses ORDER BY warehouse_id")
    
    if warehouses:
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1.5, 1.5, 1, 2])
            headers = ["ID", "仓库名称", "位置", "负责人", "联系电话", "容量", "操作"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for wh in warehouses:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 1.5, 1.5, 1, 2])
                
                with col1:
                    st.write(f"#{wh['warehouse_id']}")
                with col2:
                    st.write(f"**{wh['warehouse_name']}**")
                with col3:
                    st.write(wh['location'] or "-")
                with col4:
                    st.write(wh['manager'] or "-")
                with col5:
                    st.write(wh['phone'] or "-")
                with col6:
                    st.write(f"{wh['capacity']:,}")
                
                with col7:
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button(f"✏️", key=f"edit_wh_{wh['warehouse_id']}", use_container_width=True):
                            st.session_state.editing_warehouse = wh['warehouse_id']
                            st.rerun()
                    with btn_col2:
                        if st.button(f"🗑️", key=f"del_wh_{wh['warehouse_id']}", type="primary", use_container_width=True):
                            execute_query("DELETE FROM warehouses WHERE warehouse_id=%s", (wh['warehouse_id'],), fetch=False)
                            st.success(f"✅ 仓库 '{wh['warehouse_name']}' 删除成功！")
                            st.rerun()
        
        # 编辑表单
        if 'editing_warehouse' in st.session_state:
            edit_id = st.session_state.editing_warehouse
            edit_warehouse = next(w for w in warehouses if w['warehouse_id'] == edit_id)
            
            st.divider()
            with st.container(border=True):
                st.subheader(f"✏️ 编辑仓库: {edit_warehouse['warehouse_name']}")
                
                with st.form("edit_warehouse_form"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        new_name = st.text_input("仓库名称 *", value=edit_warehouse['warehouse_name'])
                    with col2:
                        new_location = st.text_input("仓库位置", value=edit_warehouse['location'] or "")
                    with col3:
                        new_manager = st.text_input("负责人", value=edit_warehouse['manager'] or "")
                    
                    col4, col5 = st.columns(2)
                    with col4:
                        new_phone = st.text_input("联系电话", value=edit_warehouse['phone'] or "")
                    with col5:
                        new_capacity = st.number_input("仓库容量", min_value=0, value=edit_warehouse['capacity'] or 0)
                    
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                    with col_btn1:
                        if st.form_submit_button("💾 保存", use_container_width=True):
                            execute_query("""
                                UPDATE warehouses 
                                SET warehouse_name=%s, location=%s, manager=%s, phone=%s, capacity=%s
                                WHERE warehouse_id=%s
                            """, (new_name, new_location, new_manager, new_phone, new_capacity, edit_id), fetch=False)
                            st.success("✅ 仓库更新成功！")
                            del st.session_state.editing_warehouse
                            st.rerun()
                    with col_btn2:
                        if st.form_submit_button("❌ 取消", use_container_width=True):
                            del st.session_state.editing_warehouse
                            st.rerun()
    else:
        st.info("📭 暂无仓库数据")

def show_goods_management():
    st.header("🛍️ 货物管理")
    
    # 添加新货物表单
    with st.expander("➕ 添加新货物", expanded=False):
        with st.form("add_goods_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                code = st.text_input("货物编码 *")
            with col2:
                name = st.text_input("货物名称 *")
            with col3:
                category = st.text_input("货物类别")
            
            col4, col5 = st.columns(2)
            with col4:
                unit = st.text_input("计量单位")
            with col5:
                price = st.number_input("单价 (元)", min_value=0.0, value=0.0, step=0.01)
            
            description = st.text_area("货物描述")
            
            if st.form_submit_button("添加货物", use_container_width=True, type="primary"):
                if code and name:
                    execute_query("""
                        INSERT INTO goods (goods_code, goods_name, category, unit, price, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (code, name, category, unit, price, description), fetch=False)
                    st.success("✅ 货物添加成功！")
                    st.rerun()
                else:
                    st.error("❌ 请填写货物编码和名称")
    
    st.subheader("货物列表")
    categories = execute_query(
        "SELECT DISTINCT category FROM goods WHERE category IS NOT NULL AND category <> '' ORDER BY category"
    )
    category_options = ["全部"] + [c["category"] for c in categories] if categories else ["全部"]
    selected_category = st.selectbox("按类别筛选", category_options)

    if selected_category != "全部":
        goods = execute_query("SELECT * FROM goods WHERE category=%s ORDER BY goods_id", (selected_category,))
    else:
        goods = execute_query("SELECT * FROM goods ORDER BY goods_id")
    
    if goods:
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 1.5, 2, 1.5, 1, 1.5, 2])
            headers = ["ID", "编码", "名称", "类别", "单位", "单价", "操作"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for g in goods:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 1.5, 2, 1.5, 1, 1.5, 2])
                
                with col1:
                    st.write(f"#{g['goods_id']}")
                with col2:
                    st.write(g['goods_code'])
                with col3:
                    st.write(f"**{g['goods_name']}**")
                with col4:
                    st.write(g['category'] or "-")
                with col5:
                    st.write(g['unit'] or "-")
                with col6:
                    st.write(f"¥{g['price']:.2f}" if g['price'] else "-")
                
                with col7:
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button(f"✏️", key=f"edit_gd_{g['goods_id']}", use_container_width=True):
                            st.session_state.editing_goods = g['goods_id']
                            st.rerun()
                    with btn_col2:
                        if st.button(f"🗑️", key=f"del_gd_{g['goods_id']}", type="primary", use_container_width=True):
                            execute_query("DELETE FROM goods WHERE goods_id=%s", (g['goods_id'],), fetch=False)
                            st.success(f"✅ 货物 '{g['goods_name']}' 删除成功！")
                            st.rerun()
        
        # 编辑表单
        if 'editing_goods' in st.session_state:
            edit_id = st.session_state.editing_goods
            edit_goods = next(g for g in goods if g['goods_id'] == edit_id)
            
            st.divider()
            with st.container(border=True):
                st.subheader(f"✏️ 编辑货物: {edit_goods['goods_name']}")
                
                with st.form("edit_goods_form"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        new_code = st.text_input("货物编码 *", value=edit_goods['goods_code'])
                    with col2:
                        new_name = st.text_input("货物名称 *", value=edit_goods['goods_name'])
                    with col3:
                        new_category = st.text_input("货物类别", value=edit_goods['category'] or "")
                    
                    col4, col5 = st.columns(2)
                    with col4:
                        new_unit = st.text_input("计量单位", value=edit_goods['unit'] or "")
                    with col5:
                        new_price = st.number_input("单价 (元)", min_value=0.0, value=float(edit_goods['price'] or 0), step=0.01)
                    
                    new_description = st.text_area("货物描述", value=edit_goods['description'] or "")
                    
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                    with col_btn1:
                        if st.form_submit_button("💾 保存", use_container_width=True):
                            execute_query("""
                                UPDATE goods 
                                SET goods_code=%s, goods_name=%s, category=%s, unit=%s, price=%s, description=%s
                                WHERE goods_id=%s
                            """, (new_code, new_name, new_category, new_unit, new_price, new_description, edit_id), fetch=False)
                            st.success("✅ 货物更新成功！")
                            del st.session_state.editing_goods
                            st.rerun()
                    with col_btn2:
                        if st.form_submit_button("❌ 取消", use_container_width=True):
                            del st.session_state.editing_goods
                            st.rerun()
    else:
        st.info("📭 暂无货物数据")

def show_inbound_management():
    st.header("📥 入库管理")
    
    # 新增入库表单
    with st.expander("➕ 新增入库", expanded=False):
        warehouses = execute_query("SELECT * FROM warehouses")
        goods = execute_query("SELECT * FROM goods")
        
        if warehouses and goods:
            with st.form("inbound_form"):
                col1, col2 = st.columns(2)
                with col1:
                    warehouse_options = {f"{w['warehouse_id']} - {w['warehouse_name']}": w['warehouse_id'] for w in warehouses}
                    selected_warehouse = st.selectbox("选择仓库 *", list(warehouse_options.keys()))
                with col2:
                    goods_options = {f"{g['goods_id']} - {g['goods_name']} ({g['goods_code']})": g['goods_id'] for g in goods}
                    selected_goods = st.selectbox("选择货物 *", list(goods_options.keys()))
                
                col3, col4 = st.columns(2)
                with col3:
                    quantity = st.number_input("入库数量 *", min_value=1, value=1)
                with col4:
                    operator = st.text_input("操作人员")
                
                remark = st.text_area("备注")
                
                if st.form_submit_button("确认入库", use_container_width=True, type="primary"):
                    warehouse_id = warehouse_options[selected_warehouse]
                    goods_id = goods_options[selected_goods]
                    
                    execute_query("""
                        INSERT INTO inbound_records (warehouse_id, goods_id, quantity, operator, remark)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (warehouse_id, goods_id, quantity, operator, remark), fetch=False)
                    
                    # 更新库存
                    update_inventory(warehouse_id, goods_id, quantity, is_inbound=True)
                    
                    st.success("✅ 入库成功！")
                    st.rerun()
    
    st.subheader("入库记录")
    records = execute_query("""
        SELECT i.inbound_id, w.warehouse_name, g.goods_name, g.goods_code, 
               i.quantity, i.inbound_date, i.operator, i.remark
        FROM inbound_records i
        JOIN warehouses w ON i.warehouse_id = w.warehouse_id
        JOIN goods g ON i.goods_id = g.goods_id
        ORDER BY i.inbound_date DESC
    """)
    
    if records:
        st.info("💡 提示：入库记录为业务流水，仅支持新增查询，不支持编辑删除。如需冲销，请进行出库操作。")
        
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1.5, 1, 2, 1.5])
            headers = ["ID", "仓库", "货物", "编码", "数量", "入库时间", "操作人"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for rec in records:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 1.5, 1, 2, 1.5])
                
                with col1:
                    st.write(f"#{rec['inbound_id']}")
                with col2:
                    st.write(rec['warehouse_name'])
                with col3:
                    st.write(f"**{rec['goods_name']}**")
                with col4:
                    st.write(rec['goods_code'])
                with col5:
                    st.write(f"{rec['quantity']:,}")
                with col6:
                    st.write(rec['inbound_date'].strftime('%Y-%m-%d %H:%M') if rec['inbound_date'] else "-")
                with col7:
                    st.write(rec['operator'] or "-")
    else:
        st.info("📭 暂无入库记录")

def show_outbound_management():
    st.header("📤 出库管理")
    
    # 新增出库表单
    with st.expander("➕ 新增出库", expanded=False):
        warehouses = execute_query("SELECT * FROM warehouses")
        inventory = execute_query("""
            SELECT inv.*, w.warehouse_name, g.goods_name, g.goods_code
            FROM inventory inv
            JOIN warehouses w ON inv.warehouse_id = w.warehouse_id
            JOIN goods g ON inv.goods_id = g.goods_id
            WHERE inv.quantity > 0
        """)
        
        if warehouses and inventory:
            with st.form("outbound_form"):
                inv_options = {
                    f"{i['inventory_id']} - {i['warehouse_name']} - {i['goods_name']} ({i['goods_code']}) - 库存: {i['quantity']}": 
                    (i['warehouse_id'], i['goods_id'], i['inventory_id'], i['quantity']) 
                    for i in inventory
                }
                
                selected_inv = st.selectbox("选择库存 *", list(inv_options.keys()))
                warehouse_id, goods_id, inv_id, max_qty = inv_options[selected_inv]
                
                col1, col2 = st.columns(2)
                with col1:
                    quantity = st.number_input("出库数量 *", min_value=1, max_value=max_qty, value=1)
                with col2:
                    operator = st.text_input("操作人员")
                
                remark = st.text_area("备注")
                
                if st.form_submit_button("确认出库", use_container_width=True, type="primary"):
                    execute_query("""
                        INSERT INTO outbound_records (warehouse_id, goods_id, quantity, operator, remark)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (warehouse_id, goods_id, quantity, operator, remark), fetch=False)
                    
                    # 更新库存
                    update_inventory(warehouse_id, goods_id, quantity, is_inbound=False)
                    
                    st.success("✅ 出库成功！")
                    st.rerun()
    
    st.subheader("出库记录")
    records = execute_query("""
        SELECT o.outbound_id, w.warehouse_name, g.goods_name, g.goods_code, 
               o.quantity, o.outbound_date, o.operator, o.remark
        FROM outbound_records o
        JOIN warehouses w ON o.warehouse_id = w.warehouse_id
        JOIN goods g ON o.goods_id = g.goods_id
        ORDER BY o.outbound_date DESC
    """)
    
    if records:
        st.info("💡 提示：出库记录为业务流水，仅支持新增查询，不支持编辑删除。如需冲销，请进行入库操作。")
        
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1.5, 1, 2, 1.5])
            headers = ["ID", "仓库", "货物", "编码", "数量", "出库时间", "操作人"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for rec in records:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 1.5, 1, 2, 1.5])
                
                with col1:
                    st.write(f"#{rec['outbound_id']}")
                with col2:
                    st.write(rec['warehouse_name'])
                with col3:
                    st.write(f"**{rec['goods_name']}**")
                with col4:
                    st.write(rec['goods_code'])
                with col5:
                    st.write(f"{rec['quantity']:,}")
                with col6:
                    st.write(rec['outbound_date'].strftime('%Y-%m-%d %H:%M') if rec['outbound_date'] else "-")
                with col7:
                    st.write(rec['operator'] or "-")
    else:
        st.info("📭 暂无出库记录")

def show_inventory_check():
    st.header("🔍 库存盘点")
    
    warehouses = execute_query("SELECT * FROM warehouses")
    
    col1, col2 = st.columns(2)
    with col1:
        warehouse_filter = st.selectbox("筛选仓库", ["全部"] + [f"{w['warehouse_id']} - {w['warehouse_name']}" for w in warehouses])
    with col2:
        wh_id = None
        if warehouse_filter != "全部":
            wh_id = int(warehouse_filter.split(" - ")[0])

        if wh_id is None:
            goods = execute_query("SELECT * FROM goods ORDER BY goods_id")
        else:
            goods = execute_query("""
                SELECT DISTINCT g.*
                FROM inventory inv
                JOIN goods g ON inv.goods_id = g.goods_id
                WHERE inv.warehouse_id = %s
                ORDER BY g.goods_id
            """, (wh_id,))

        goods_filter = st.selectbox("筛选货物", ["全部"] + [f"{g['goods_id']} - {g['goods_name']}" for g in goods])
    
    query = """
        SELECT inv.*, w.warehouse_name, g.goods_name, g.goods_code, g.unit
        FROM inventory inv
        JOIN warehouses w ON inv.warehouse_id = w.warehouse_id
        JOIN goods g ON inv.goods_id = g.goods_id
        WHERE 1=1
    """
    params = []
    
    if warehouse_filter != "全部":
        wh_id = int(warehouse_filter.split(" - ")[0])
        query += " AND inv.warehouse_id = %s"
        params.append(wh_id)
    
    if goods_filter != "全部":
        g_id = int(goods_filter.split(" - ")[0])
        query += " AND inv.goods_id = %s"
        params.append(g_id)
    
    inventory = execute_query(query, params)
    
    if inventory:
        # 计算差异
        for item in inventory:
            item['差异'] = item['actual_quantity'] - item['quantity']
            if item['差异'] > 0:
                item['差异状态'] = '盘盈'
            elif item['差异'] < 0:
                item['差异状态'] = '盘亏'
            else:
                item['差异状态'] = '正常'
        
        st.subheader("📋 库存详情")
        
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5, 1, 1, 1.5])
            headers = ["ID", "仓库", "货物", "编码", "单位", "账面数量", "实际数量", "差异", "差异状态", "操作"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for item in inventory:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7, col8, col9, col10 = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5, 1, 1, 1.5])
                
                with col1:
                    st.write(f"#{item['inventory_id']}")
                with col2:
                    st.write(item['warehouse_name'])
                with col3:
                    st.write(f"**{item['goods_name']}**")
                with col4:
                    st.write(item['goods_code'])
                with col5:
                    st.write(item['unit'])
                with col6:
                    st.write(f"{item['quantity']:,}")
                with col7:
                    st.write(f"{item['actual_quantity']:,}")
                with col8:
                    diff = item['差异']
                    if diff > 0:
                        st.markdown(f"<span style='color:green'>+{diff}</span>", unsafe_allow_html=True)
                    elif diff < 0:
                        st.markdown(f"<span style='color:red'>{diff}</span>", unsafe_allow_html=True)
                    else:
                        st.write('0')
                with col9:
                    st.write(item['差异状态'])
                with col10:
                    if st.button("✏️调整", key=f"adjust_{item['inventory_id']}", use_container_width=True):
                        st.session_state.adjusting_inventory = item['inventory_id']
                        st.rerun()
        
        # 调整表单
        if 'adjusting_inventory' in st.session_state:
            inv_id = st.session_state.adjusting_inventory
            selected_item = next(i for i in inventory if i['inventory_id'] == inv_id)
            
            st.divider()
            with st.container(border=True):
                st.subheader("✏️ 盘点调整")
                
                with st.form("adjust_form"):
                    st.write(f"**仓库**: {selected_item['warehouse_name']}")
                    st.write(f"**货物**: {selected_item['goods_name']} ({selected_item['goods_code']})")
                    st.write(f"**当前账面数量**: {selected_item['quantity']:,}")
                    st.write(f"**当前实际数量**: {selected_item['actual_quantity']:,}")
                    
                    new_actual = st.number_input("新的实际库存数量 *", min_value=0, value=selected_item['actual_quantity'])
                    remark = st.text_area("盘点备注")
                    
                    col_btn1, col_btn2 = st.columns([1,1])
                    with col_btn1:
                        if st.form_submit_button("💾 确认调整", use_container_width=True, type="primary"):
                            execute_query("""
                                UPDATE inventory SET actual_quantity = %s WHERE inventory_id = %s
                            """, (new_actual, inv_id), fetch=False)
                            st.success("✅ 盘点调整成功！")
                            del st.session_state.adjusting_inventory
                            st.rerun()
                    with col_btn2:
                        if st.form_submit_button("❌ 取消", use_container_width=True):
                            del st.session_state.adjusting_inventory
                            st.rerun()
    else:
        st.info("📭 暂无库存数据")

def show_age_analysis():
    st.header("📊 库龄分析")
    
    warehouses = execute_query("SELECT * FROM warehouses")
    warehouse_filter = st.selectbox("筛选仓库", ["全部"] + [f"{w['warehouse_id']} - {w['warehouse_name']}" for w in warehouses])
    
    query = """
        SELECT inv.*, w.warehouse_name, g.goods_name, g.goods_code, g.unit
        FROM inventory inv
        JOIN warehouses w ON inv.warehouse_id = w.warehouse_id
        JOIN goods g ON inv.goods_id = g.goods_id
        WHERE inv.quantity > 0
    """
    params = []
    
    if warehouse_filter != "全部":
        wh_id = int(warehouse_filter.split(" - ")[0])
        query += " AND inv.warehouse_id = %s"
        params.append(wh_id)
    
    inventory = execute_query(query, params)
    
    if inventory:
        # 计算库龄
        for item in inventory:
            if item['last_in_time']:
                item['库龄(天)'] = (datetime.now() - item['last_in_time']).days
            else:
                item['库龄(天)'] = None
                
            if item['库龄(天)'] is None:
                item['库龄分组'] = '未知'
            elif item['库龄(天)'] <= 7:
                item['库龄分组'] = '0-7天'
            elif item['库龄(天)'] <= 30:
                item['库龄分组'] = '8-30天'
            elif item['库龄(天)'] <= 90:
                item['库龄分组'] = '31-90天'
            elif item['库龄(天)'] <= 180:
                item['库龄分组'] = '91-180天'
            else:
                item['库龄分组'] = '180天以上'
        
        st.subheader("📋 库龄详情")
        
        # 表头
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5, 1.5, 2])
            headers = ["ID", "仓库", "货物", "编码", "单位", "库存数量", "库龄(天)", "库龄分组", "最后入库"]
            for col, header in zip(cols, headers):
                col.markdown(f"**{header}**")
        
        # 数据行
        for item in inventory:
            with st.container(border=True):
                col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5, 1.5, 2])
                
                with col1:
                    st.write(f"#{item['inventory_id']}")
                with col2:
                    st.write(item['warehouse_name'])
                with col3:
                    st.write(f"**{item['goods_name']}**")
                with col4:
                    st.write(item['goods_code'])
                with col5:
                    st.write(item['unit'])
                with col6:
                    st.write(f"{item['quantity']:,}")
                with col7:
                    if item['库龄(天)']:
                        st.write(f"{item['库龄(天)']}天")
                    else:
                        st.write("-")
                with col8:
                    st.write(item['库龄分组'])
                with col9:
                    if item['last_in_time']:
                        st.write(item['last_in_time'].strftime('%Y-%m-%d %H:%M'))
                    else:
                        st.write("-")
        
        st.divider()
        st.subheader("📈 库龄统计")
        
        # 统计数据
        df = pd.DataFrame(inventory)
        age_stats = df.groupby('库龄分组').agg({
            'quantity': 'sum',
            'goods_code': 'count'
        }).rename(columns={'quantity': '总库存', 'goods_code': '货物种类数'})
        st.bar_chart(age_stats['总库存'])
        
        st.divider()
        st.subheader("⚠️ 超期库存预警")
        
        overdue = [item for item in inventory if item['库龄(天)'] and item['库龄(天)'] > 90]
        if len(overdue) > 0:
            st.warning(f"发现 {len(overdue)} 种库存超过90天！")
            
            with st.container(border=True):
                cols = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5])
                headers = ["ID", "仓库", "货物", "编码", "单位", "库存数量", "库龄(天)"]
                for col, header in zip(cols, headers):
                    col.markdown(f"**{header}**")
            
            for item in overdue:
                with st.container(border=True):
                    col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 1.5, 1, 1.5, 1.5])
                    
                    with col1:
                        st.write(f"#{item['inventory_id']}")
                    with col2:
                        st.write(item['warehouse_name'])
                    with col3:
                        st.write(f"**{item['goods_name']}**")
                    with col4:
                        st.write(item['goods_code'])
                    with col5:
                        st.write(item['unit'])
                    with col6:
                        st.write(f"{item['quantity']:,}")
                    with col7:
                        st.write(f"{item['库龄(天)']}天")
        else:
            st.success("✅ 没有超过90天的库存")
    else:
        st.info("📭 暂无库存数据")

def show_statistics():
    st.header("📈 统计报表")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📦 各仓库库存统计")
        warehouse_stats = execute_query("""
            SELECT w.warehouse_name, SUM(inv.quantity) as total_quantity, COUNT(DISTINCT inv.goods_id) as goods_count
            FROM warehouses w
            LEFT JOIN inventory inv ON w.warehouse_id = inv.warehouse_id
            GROUP BY w.warehouse_id, w.warehouse_name
        """)
        if warehouse_stats:
            df_wh = pd.DataFrame(warehouse_stats)
            df_wh_renamed = df_wh.rename(columns={
                'warehouse_name': '仓库名称',
                'total_quantity': '总库存',
                'goods_count': '货物种类数'
            })
            st.dataframe(df_wh_renamed, use_container_width=True)
            st.bar_chart(df_wh.set_index('warehouse_name')['total_quantity'])
    
    with col2:
        st.subheader("📂 货物分类统计")
        category_stats = execute_query("""
            SELECT g.category, SUM(inv.quantity) as total_quantity, COUNT(DISTINCT g.goods_id) as goods_count
            FROM goods g
            LEFT JOIN inventory inv ON g.goods_id = inv.goods_id
            GROUP BY g.category
        """)
        if category_stats:
            df_cat = pd.DataFrame(category_stats)
            df_cat_renamed = df_cat.rename(columns={
                'category': '货物分类',
                'total_quantity': '总库存',
                'goods_count': '货物种类数'
            })
            st.dataframe(df_cat_renamed, use_container_width=True)
    
    st.divider()
    st.subheader("📊 出入库趋势（最近30天）")
    trend_data = execute_query("""
        SELECT 
            DATE(t.date) as date,
            COALESCE(SUM(t.inbound), 0) as inbound_total,
            COALESCE(SUM(t.outbound), 0) as outbound_total
        FROM (
            SELECT inbound_date as date, quantity as inbound, 0 as outbound FROM inbound_records
            WHERE inbound_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            UNION ALL
            SELECT outbound_date as date, 0 as inbound, quantity as outbound FROM outbound_records
            WHERE outbound_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        ) t
        GROUP BY DATE(t.date)
        ORDER BY date
    """)
    if trend_data:
        df_trend = pd.DataFrame(trend_data)
        df_trend_renamed = df_trend.rename(columns={
            'date': '日期',
            'inbound_total': '入库总量',
            'outbound_total': '出库总量'
        })
        st.dataframe(df_trend_renamed, use_container_width=True)
        df_trend['date'] = pd.to_datetime(df_trend['date'])
        df_trend = df_trend.set_index('date')
        st.line_chart(df_trend)
    
    st.divider()
    st.subheader("🏆 货物库存TOP10")
    top_goods = execute_query("""
        SELECT g.goods_name, g.goods_code, SUM(inv.quantity) as total_quantity
        FROM goods g
        JOIN inventory inv ON g.goods_id = inv.goods_id
        GROUP BY g.goods_id, g.goods_name, g.goods_code
        ORDER BY total_quantity DESC
        LIMIT 10
    """)
    if top_goods:
        df_top = pd.DataFrame(top_goods)
        df_top_renamed = df_top.rename(columns={
            'goods_name': '货物名称',
            'goods_code': '货物编码',
            'total_quantity': '总库存'
        })
        st.dataframe(df_top_renamed, use_container_width=True)
        st.bar_chart(df_top.set_index('goods_name')['total_quantity'])

if __name__ == "__main__":
    main()
