import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, date
import base64
import plotly.express as px

# --- データベース設定 ---
DB_NAME = 'mahjong_stats_v34.db'
def get_user_full_info(name):
    """ユーザーのアイコン、所属、実名をDBから取得しHTML要素として返す"""
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute('SELECT icon, organization, real_name FROM users WHERE username=?', (name,)).fetchone()
    
    if res:
        icon_src = res[0]
        # アイコンがBase64画像（長い文字列）か絵文字かを判定
        if len(icon_src) > 10:
            icon_html = f'<img src="{icon_src}" style="width:35px; height:35px; border-radius:50%; object-fit:cover;">'
        else:
            icon_html = f'<div style="width:35px; height:35px; border-radius:50%; background:#ddd; display:flex; align-items:center; justify-content:center;">{icon_src}</div>'
        
        return {"icon_html": icon_html, "org": res[1], "real_name": res[2]}
    
    # データがない場合のデフォルト
    return {"icon_html": "👤", "org": "Guest", "real_name": name}

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT, real_name TEXT, 
                     icon TEXT, birthday TEXT, gender TEXT, organization TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS groups 
                     (group_name TEXT PRIMARY KEY, members TEXT, default_rule TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS matches 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, group_name TEXT, rule_name TEXT, mode TEXT, 
                  date TEXT, day_key TEXT, players TEXT, scores TEXT, p_scores TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS friends 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                sender TEXT, receiver TEXT, status TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS messages 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                sender TEXT, receiver TEXT, content TEXT, 
                image_data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def calculate_age(birth_str):
    try:
        birth = datetime.strptime(birth_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    except: return "??"

def get_user_icon(name):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute('SELECT icon FROM users WHERE username=?', (name,)).fetchone()
    if res and len(res[0]) > 5:
        return f'<img src="{res[0]}" style="width:22px; height:22px; border-radius:50%; margin-right:5px; vertical-align:middle;">'
    return f'<span style="margin-right:5px; vertical-align:middle;">{res[0] if res else "👤"}</span>'

def calculate_precise_points(scores, rule, mode):
    num_p = len(scores)
    ranked_indices = sorted(range(num_p), key=lambda x: (scores[x], -x), reverse=True)
    p_pts = [0.0] * num_p
    
    if mode == "4人打ち":
        if rule == "連盟公式":
            uki_count = sum(1 for s in scores if s >= 30000)
            uma_table = {0:[0,0,0,0], 1:[12.0,-1.0,-3.0,-8.0], 2:[8.0,4.0,-4.0,-8.0], 3:[8.0,3.0,1.0,-12.0], 4:[0,0,0,0]}
            uma = uma_table.get(uki_count, [0,0,0,0])
            for i in range(num_p):
                p_pts[i] = (scores[i] - 30000) / 1000 + uma[ranked_indices.index(i)]
        else:
            base_return = 30000 
            uma = [30.0, 10.0, -10.0, -30.0]
            for i in range(num_p):
                p_pts[i] = (scores[i] - base_return) / 1000 + uma[ranked_indices.index(i)]
            if rule == "Mリーグ": p_pts[ranked_indices[0]] += 20.0
    else: # 3人打ち
        uma = [35.0, 0.0, -20.0]
        for i in range(num_p):
            p_pts[i] = (scores[i] - 40000) / 1000 + uma[ranked_indices.index(i)]
    return [round(p, 1) for p in p_pts]

# --- UI & CSS ---
st.set_page_config(page_title="Mahjong Result System", layout="wide")
init_db()

st.markdown("""
    <style>
    .stApp { background-color: #FFF9FA; }
    h1, h2, h3 { color: #E91E63 !important; font-weight: bold; }
    .stButton>button {
        background: linear-gradient(to right, #FF69B4, #FF1493); color: white;
        border-radius: 20px; border: none; padding: 10px 20px; font-weight: bold; width: 100%;
    }
    .match-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #FF69B4; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 10px; }
    .free-item { background: #FFFFFF; padding: 12px; border-radius: 8px; border: 1px solid #FFD1DC; margin-bottom: 8px; font-size: 0.9rem; }
    .kyotaku-badge { background: #F3F4F6; color: #6B7280; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px; border: 1px solid #D1D5DB; }
    </style>
    """, unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'real_name': None, 
        'icon': "🀄", 'org': "フリー", 'birth': "2000-01-01", 'gender': "未設定",
        'selected_group': "フリー入力", 'reset_counter': 0
    })

def main():
    if not st.session_state['logged_in']:
        st.title("💖 Mahjong System")
        t1, t2 = st.tabs(["🔑 ログイン", "📝 新規登録"])
        with t1:
            l_u = st.text_input("ID", key="login_id")
            l_p = st.text_input("パスワード", type='password', key="login_pw")
            if st.button("ログイン"):
                with sqlite3.connect(DB_NAME) as conn:
                    res = conn.execute('SELECT password, real_name, icon, organization, birthday, gender FROM users WHERE username=?', (l_u,)).fetchone()
                if res and check_hashes(l_p, res[0]):
                    st.session_state.update({'logged_in': True, 'user': l_u, 'real_name': res[1], 'icon': res[2], 'org': res[3], 'birth': res[4], 'gender': res[5]})
                    loading_screen("読み込み中...")
                    st.rerun()
                else: st.error("ログイン情報に誤りがあります")
        with t2:
            with st.form("registration_form"):
                s_u, s_r, s_p = st.text_input("ニックネーム(ログインID)"), st.text_input("本名"), st.text_input("パスワード", type='password')
                s_o = st.selectbox("所属団体", ["未所属", "日本プロ麻雀連盟", "最高位戦日本プロ麻雀協会", "日本プロ麻雀協会", "RMU", "麻将連合-μ-"])
                s_birth = st.date_input(
                    "生年月日", 
                    value=date(2000, 1, 1),
                    min_value=date(1920, 1, 1), 
                    max_value=date(2030, 12, 31)
                )
                s_gen = st.radio("性別", ["男性", "女性", "その他", "未設定"], horizontal=True)
                if st.form_submit_button("登録する"):
                    if s_u and s_r and s_p:
                        with sqlite3.connect(DB_NAME) as conn:
                            if conn.execute('SELECT 1 FROM users WHERE username=?', (s_u,)).fetchone():
                                st.error("このIDは既に使用されています")
                            else:
                                b_str = s_birth.strftime("%Y-%m-%d")
                                conn.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?)', (s_u, make_hashes(s_p), s_r, "🀄", b_str, s_gen, s_o))
                                conn.commit()
                                st.session_state.update({'logged_in': True, 'user': s_u, 'real_name': s_r, 'icon': "🀄", 'org': s_o, 'birth': b_str, 'gender': s_gen})
                                st.success("登録完了！")
                                loading_screen("読み込み中...")
                                st.rerun()
    else:
        # --- Sidebar ---
        age = calculate_age(st.session_state['birth'])
        st.sidebar.markdown(f"### {get_user_icon(st.session_state['user'])} {st.session_state['user']}", unsafe_allow_html=True)
        st.sidebar.write(f"👤 **{st.session_state['real_name']}** ({st.session_state['gender']}/{age}歳)")
        st.sidebar.write(f"🏢 **{st.session_state['org']}**")
        with st.sidebar.expander("⚙️ プロフィール編集"):
            # --- 入力項目の設定 ---
            u_name = st.text_input("ニックネーム（ID）", value=st.session_state['user'])
            u_real = st.text_input("名前（実名）", value=st.session_state['real_name'])
            
            # パスワード変更欄（空欄なら変更しない）
            new_pass = st.text_input("新しいパスワード（変更する場合のみ入力）", type='password')
            
            org_list = ["未所属", "日本プロ麻雀連盟", "最高位戦日本プロ麻雀協会", "日本プロ麻雀協会", "RMU", "麻将連合-μ-"]
            u_org = st.selectbox("所属", org_list, index=org_list.index(st.session_state['org']) if st.session_state['org'] in org_list else 0)
            u_birth = st.date_input(
                "生年月日", 
                value=datetime.strptime(st.session_state['birth'], "%Y-%m-%d"),
                min_value=date(1920, 1, 1),
                max_value=date(2030, 12, 31)
            )
            u_gen = st.radio("性別", ["男性", "女性", "その他", "未設定"], index=["男性", "女性", "その他", "未設定"].index(st.session_state['gender']))
            u_img = st.file_uploader("アイコン", type=['png', 'jpg'])
            
            if st.button("プロフィールを更新"):
                old_name = st.session_state['user']
                icon_data = st.session_state['icon']
                if u_img: icon_data = f"data:image/png;base64,{base64.b64encode(u_img.read()).decode()}"
                b_str = u_birth.strftime("%Y-%m-%d")
                
                with sqlite3.connect(DB_NAME) as conn:
                    # 1. 重複チェック
                    if u_name != old_name:
                        check = conn.execute('SELECT 1 FROM users WHERE username=?', (u_name,)).fetchone()
                        if check:
                            st.error("そのニックネームは既に使われています")
                            st.stop()
                    
                    # 2. パスワードの更新判定
                    if new_pass:
                        # 新しいパスワードが入力された場合はハッシュ化して更新
                        hashed_new_pass = make_hashes(new_pass)
                        conn.execute('UPDATE users SET username=?, password=?, real_name=?, icon=?, organization=?, birthday=?, gender=? WHERE username=?', 
                                     (u_name, hashed_new_pass, u_real, icon_data, u_org, b_str, u_gen, old_name))
                    else:
                        # 入力がない場合はパスワードはそのまま
                        conn.execute('UPDATE users SET username=?, real_name=?, icon=?, organization=?, birthday=?, gender=? WHERE username=?', 
                                     (u_name, u_real, icon_data, u_org, b_str, u_gen, old_name))
                    
                    # 3. 関連データの更新（ID変更対応）
                    matches = conn.execute('SELECT id, players FROM matches WHERE players LIKE ?', (f'%{old_name}%',)).fetchall()
                    for m_id, p_list in matches:
                        new_p_list = ",".join([u_name if p == old_name else p for p in p_list.split(",")])
                        conn.execute('UPDATE matches SET players=? WHERE id=?', (new_p_list, m_id))
                    
                    conn.execute('UPDATE friends SET sender=? WHERE sender=?', (u_name, old_name))
                    conn.execute('UPDATE friends SET receiver=? WHERE receiver=?', (u_name, old_name))
                    conn.execute('UPDATE messages SET sender=? WHERE sender=?', (u_name, old_name))
                    conn.execute('UPDATE messages SET receiver=? WHERE receiver=?', (u_name, old_name))
                    
                    conn.commit()
                
                # セッション情報の更新
                st.session_state.update({'user': u_name, 'real_name': u_real, 'icon': icon_data, 'org': u_org, 'birth': b_str, 'gender': u_gen})
                st.success("プロフィールを更新しました！")
                st.rerun()
            st.markdown("---")
            st.warning("⚠️ 危険な操作")
            if st.checkbox("アカウントを削除する"):
                st.error("一度削除すると、これまでの全ての対局データがあなたの名前で集計できなくなります。")
                if st.button("本当にアカウントを完全に削除する"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute('DELETE FROM users WHERE username=?', (st.session_state['user'],))
                        conn.commit()
                    st.session_state.clear()
                    st.success("アカウントを削除しました。")
                    st.rerun()
        if st.sidebar.button("ログアウト"):
            st.session_state.clear()
            loading_screen("ログアウト中...")
            st.rerun()

        # --- Menu Selection ---
        if 'active_page' not in st.session_state:
            st.session_state['active_page'] = "🎮 対局入力"

        pages = ["🎮 対局入力", "📊 履歴・分析", "👥 グループ", "🤝 フレンド"]
        selected = st.radio("Menu", pages, 
                            index=pages.index(st.session_state['active_page']), 
                            horizontal=True, label_visibility="collapsed")
        # ここに追加（メニューが変わったら一度クリアする）
        if selected != st.session_state['active_page']:
            st.empty()
        st.session_state['active_page'] = selected
        st.divider()

        # --- Page Routing ---
        if st.session_state['active_page'] == "🎮 対局入力":
            st.header("🎮 対局入力")
            c1, c2 = st.columns(2)

            # --- 1. グループ選択肢の準備 ---
            current_user = st.session_state['user']
            with sqlite3.connect(DB_NAME) as conn:
                query = "SELECT group_name FROM groups WHERE members LIKE ?"
                gs = pd.read_sql(query, conn, params=(f'%{current_user}%',))
            g_list = ["フリー入力"] + gs['group_name'].tolist()

            # --- 2. 管理画面からの遷移・自動反映ロジック (追加/修正) ---
            # 初期インデックスの決定
            default_g_index = 0
            
            # 管理画面で「このセットを開始」が押された場合
            if 'selected_group_from_manage' in st.session_state:
                target_g = st.session_state['selected_group_from_manage']
                if target_g in g_list:
                    default_g_index = g_list.index(target_g)
                # 一度反映させたら、次回リロード時はそのグループを維持するか、
                # もしくは del st.session_state['selected_group_from_manage'] してリセットする
                # ここでは反映を優先するため一旦維持、または処理後に削除を検討してください。

            # 対局グループセレクトボックス
            sel_g = c1.selectbox(
                "対局グループ", 
                g_list, 
                index=default_g_index, # 計算したインデックスを適用
                key=f"sel_g_main_{st.session_state.reset_counter}"
            )

            # --- 3. ルール設定の自動反映ロジック ---
            rule_options = ["連盟公式", "Mリーグ", "一般(競技)", "3麻標準"]
            auto_rule = "連盟公式"

            # ① グループが選ばれたらDBからデフォルトルールを取得
            if sel_g != "フリー入力":
                with sqlite3.connect(DB_NAME) as conn:
                    res = conn.execute('SELECT default_rule FROM groups WHERE group_name=?', (sel_g,)).fetchone()
                    if res and res[0]:
                        auto_rule = res[0]
            
            # ② 管理画面からのルール指定がある場合は上書き
            if 'selected_rule_from_manage' in st.session_state:
                auto_rule = st.session_state['selected_rule_from_manage']
                # ルールは一度適用したら消去してOK
                del st.session_state['selected_rule_from_manage']
                # ※グループ名の方も、反映が終わったこのタイミングで消すと安全です
                if 'selected_group_from_manage' in st.session_state:
                    del st.session_state['selected_group_from_manage']

            try:
                rule_idx = rule_options.index(auto_rule)
            except ValueError:
                rule_idx = 0

            rule = c2.selectbox("ルール設定", rule_options, index=rule_idx, key=f"rule_sel_{st.session_state.reset_counter}_{sel_g}")
            # -----------------------------------------------

            if rule == "連盟公式": def_sc, mode, num_p, total_base = 30000, "4人打ち", 4, 120000
            # ...（以下、元のコードが続く）

            if rule == "連盟公式": def_sc, mode, num_p, total_base = 30000, "4人打ち", 4, 120000
            elif rule == "3麻標準": def_sc, mode, num_p, total_base = 35000, "3人打ち", 3, 105000
            else: def_sc, mode, num_p, total_base = 25000, "4人打ち", 4, 100000

            m_list = pd.read_sql('SELECT username FROM users', sqlite3.connect(DB_NAME))['username'].tolist()
            # --- プレイヤー選択肢の動的制御 ---
            if sel_g == "フリー入力":
                # 全ユーザー + その他
                m_list = pd.read_sql('SELECT username FROM users', sqlite3.connect(DB_NAME))['username'].tolist()
                p_options = sorted(list(set(m_list))) + ["その他"]
            else:
                # グループメンバーのみ取得 + その他
                with sqlite3.connect(DB_NAME) as conn:
                    g_res = conn.execute('SELECT members FROM groups WHERE group_name=?', (sel_g,)).fetchone()
                if g_res:
                    p_options = sorted(g_res[0].split(',')) + ["その他"]
                else:
                    p_options = ["その他"]
            # --- プレイヤー選択肢の初期値を決定するロジック ---
            initial_indices = []
            for i in range(num_p):
                # 選択肢の数（その他を除く）より現在の枠が少ない場合は順番に割り当て
                if i < len(p_options) - 1:
                    initial_indices.append(i)
                else:
                    # メンバーが足りない場合は「その他」のインデックスを割り当て
                    initial_indices.append(p_options.index("その他"))

            p_names, p_scores = [], []
            cols = st.columns(num_p)
            for i in range(num_p):
                with cols[i]:
                    # index=initial_indices[i] を使うことで重複を避ける
                    sel_p = st.selectbox(
                        f"Player{i+1}", 
                        p_options, 
                        index=initial_indices[i], 
                        key=f"p{i}_{st.session_state.reset_counter}_{rule}_{sel_g}" # sel_gをkeyに含めてリセットを確実に
                    )
                    
                    p_name = st.text_input(
                        f"氏名{i+1}", 
                        key=f"n{i}_{st.session_state.reset_counter}_{rule}_{sel_g}"
                    ) if sel_p == "その他" else sel_p
                    
                    p_names.append(p_name)
                    p_scores.append(st.number_input(f"持ち点", step=100, value=def_sc, key=f"s{i}_{st.session_state.reset_counter}_{rule}_{sel_g}"))

            current_total = sum(p_scores)
            kyotaku = total_base - current_total
            st.info(f"現在の合計点: {current_total} / 供託残: {kyotaku}")

            if st.button("この対局を保存"):
                current_user = st.session_state['user']
                
                # --- ① 自分のアカウントが含まれているかチェック ---
                if current_user not in p_names:
                    st.error(f"❌ あなた（{current_user}）が含まれていない対局は保存できません。")
                
                # 同一アカウントチェック
                elif len([n for n in p_names if n != "その他"]) != len(set([n for n in p_names if n != "その他"])):
                    st.error("❌ エラー：同じアカウントが複数選択されています。")
                
                else:
                    # --- ② グループ対局のメンバー制限チェック ---
                    is_valid_group_members = True
                    if sel_g != "フリー入力":
                        # 現在のグループの登録メンバーを取得
                        with sqlite3.connect(DB_NAME) as conn:
                            g_data = conn.execute('SELECT members FROM groups WHERE group_name=?', (sel_g,)).fetchone()
                        
                        if g_data:
                            allowed_members = g_data[0].split(',') + ["その他"]
                            invalid_players = [p for p in p_names if p not in allowed_members]
                            
                            if invalid_players:
                                st.error(f"❌ グループ外のユーザーが含まれています: {', '.join(invalid_players)}")
                                st.info(f"このグループのメンバー: {g_data[0]}")
                                is_valid_group_members = False
                    
                    # すべてのチェックを通過した場合のみ保存
                    if is_valid_group_members:
                        loading_screen("データを記録しています...")
                        pts = calculate_precise_points(p_scores, rule, mode)
                        now = datetime.now()
                        d_key = f"{now.strftime('%Y%m%d')}_{sel_g}_{rule}"
                        
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute('INSERT INTO matches (group_name, rule_name, mode, date, day_key, players, scores, p_scores) VALUES (?,?,?,?,?,?,?,?)',
                                         (sel_g, rule, mode, now.strftime("%Y/%m/%d %H:%M"), d_key, ",".join(p_names), ",".join(map(str, p_scores)), ",".join(map(str, pts))))
                            conn.commit()
                        
                        st.session_state.reset_counter += 1
                        st.success("対局を保存しました！")
                        st.rerun()

        # 2. 履歴・分析ページ
        elif st.session_state['active_page'] == "📊 履歴・分析":
            st.header("📊 対局履歴・分析")
            # ASCで読み込み（計算用）
            df_base = pd.read_sql('SELECT * FROM matches ORDER BY id ASC', sqlite3.connect(DB_NAME))
            
            if not df_base.empty:
                my = st.session_state['user']
                
                # --- 1. フィルタリング機能 ---
                with st.expander("🔍 履歴を検索・絞り込み"):
                    f_col1, f_col2 = st.columns(2)
                    all_rules = ["すべて"] + sorted(df_base['rule_name'].unique().tolist())
                    target_rule = f_col1.selectbox("ルールで絞り込み", all_rules)
                    all_groups = ["すべて"] + sorted(df_base['group_name'].unique().tolist())
                    target_group = f_col2.selectbox("対局グループで絞り込み", all_groups)

                df = df_base.copy()
                if target_rule != "すべて": df = df[df['rule_name'] == target_rule]
                if target_group != "すべて": df = df[df['group_name'] == target_group]
                
                my_df = df[df['players'].apply(lambda x: my in x.split(","))].copy()
                
                # --- 2. 個人通算成績の計算 ---
                if not my_df.empty:
                    sum_st = {'g':0, 'p':0.0, 'r':0, '1':0, '2':0, '3':0, '4':0}
                    for _, row in my_df.iterrows():
                        ps = row['players'].split(",")
                        sc = [float(s) for s in row['scores'].split(",")]
                        idx = ps.index(my)
                        rk = sorted(sc, reverse=True).index(sc[idx]) + 1
                        sum_st['g'] += 1
                        sum_st['p'] += float(row['p_scores'].split(",")[idx])
                        sum_st['r'] += rk
                        sum_st[str(rk) if rk < 5 else '4'] += 1
                    
                    st.subheader("個人通算成績")
                    mc = st.columns(5)
                    mc[0].metric("トータルPt", f"{round(sum_st['p'],1)}")
                    mc[1].metric("平均順位", f"{round(sum_st['r']/sum_st['g'],2)}")
                    mc[2].metric("トップ率", f"{round(sum_st['1']/sum_st['g']*100,1)}%")
                    mc[3].metric("連対率", f"{round((sum_st['1']+sum_st['2'])/sum_st['g']*100,1)}%")
                    mc[4].metric("ラス回避", f"{round((1-sum_st['4']/sum_st['g'])*100,1)}%")
                
                st.divider()

                # --- 3. 履歴表示 ---
                if not my_df.empty:
                    sorted_my_df = my_df.sort_values('id', ascending=False)
                    for d_key, g_df in sorted_my_df.groupby('day_key', sort=False):
                        g_name = g_df.iloc[0]['group_name']
                        
                        if g_name == "フリー入力":
                            st.subheader(f"📅 フリー入力履歴 ({len(g_df)}戦)")
                            for _, row in g_df.iterrows():
                                # フリー入力用の表示
                                pl, sc, pt = row['players'].split(','), row['scores'].split(','), row['p_scores'].split(',')
                                
                                # コンテナを作成して、表示と削除ボタンをまとめる
                                with st.container():
                                    st.markdown(f'''
                                        <div style="background:white; padding:10px; border-radius:5px; border-left:5px solid #1A237E; margin-bottom:0px;">
                                            <b>{row["date"]}</b> | {row["rule_name"]} (ID: {row["id"]})<br>
                                            {" / ".join([f"{n}: {s}({p}pt)" for n,s,p in zip(pl, sc, pt)])}
                                        </div>
                                    ''', unsafe_allow_html=True)
                                    
                                    # 個別削除ボタン（小さめに配置）
                                    if st.button(f"🗑️ ID:{row['id']} を削除", key=f"del_free_{row['id']}"):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            conn.execute('DELETE FROM matches WHERE id=?', (row['id'],))
                                        st.rerun()
                                    st.markdown("<br>", unsafe_allow_html=True)
                        else:
                            # 【セット対局】
                            with st.expander(f"🏆 セット: {g_name} | {g_df.iloc[0]['date'][:10]} ({len(g_df)}戦)", expanded=True):
                                players = g_df.iloc[0]['players'].split(',')
                                
                                # 初期化
                                table_html = '<table class="pro-table"><tr><th>回</th>'
                                for p in players:
                                    info = get_user_full_info(p)
                                    table_html += f'<th>{info["icon_html"]}<br>{p}</th>'
                                table_html += '<th>消</th></tr>'
                                
                                cum_pts = {p: 0.0 for p in players}
                                plot_data = []
                                # 起点0を追加
                                for p in players:
                                    plot_data.append({'戦': 0, 'Player': p, 'Total': 0.0})

                                # 対局データを1つのループで処理
                                for i, (_, row) in enumerate(g_df.sort_values('id').iterrows()):
                                    ps, ss, pts = row['players'].split(','), row['scores'].split(','), row['p_scores'].split(',')
                                    
                                    table_html += f'<tr><td>{i+1}</td>'
                                    for p in players:
                                        if p in ps:
                                            idx = ps.index(p)
                                            val, sc = float(pts[idx]), ss[idx]
                                            cum_pts[p] += val
                                            plot_data.append({'戦': i+1, 'Player': p, 'Total': round(cum_pts[p], 1)})
                                            
                                            cls = "pt-plus" if val >= 0 else "pt-minus"
                                            table_html += f'<td><div class="{cls}">{"+" if val>0 else ""}{val}</div><div class="score-sub">{int(float(sc)):,}</div></td>'
                                        else:
                                            table_html += '<td>-</td>'
                                    table_html += f'<td><small>ID:{row["id"]}</small></td></tr>'
                                
                                table_html += '</table>'
                                st.write(table_html, unsafe_allow_html=True)

                                # 削除操作
                                target_del = st.selectbox("削除する対局ID", g_df['id'].tolist(), key=f"del_sel_{d_key}")
                                if st.button("🗑️ 選択した対局を削除", key=f"del_btn_{d_key}"):
                                    with sqlite3.connect(DB_NAME) as conn:
                                        conn.execute('DELETE FROM matches WHERE id=?', (target_del,))
                                    st.rerun()

                                # ランキング
                                st.subheader("🏁 セット最終順位")
                                for r, (p, pt) in enumerate(sorted(cum_pts.items(), key=lambda x:x[1], reverse=True), 1):
                                    info = get_user_full_info(p)
                                    cls = "pt-plus" if pt >= 0 else "pt-minus"
                                    st.markdown(f'<div class="rank-card"><div class="rank-num">{r}</div>{info["icon_html"]}'
                                                f'<div style="margin-left:15px;"><b>{p}</b><br><small>{info["org"]}</small></div>'
                                                f'<div class="total-pt {cls}">{"+" if pt>0 else ""}{round(pt,1)}</div></div>', unsafe_allow_html=True)
                                
                                # グラフ描画
                                fig = px.line(pd.DataFrame(plot_data), x='戦', y='Total', color='Player', markers=True)
                                fig.update_layout(
                                    xaxis=dict(dtick=1),
                                    paper_bgcolor='rgba(0,0,0,0)', 
                                    plot_bgcolor='rgba(0,0,0,0)'
                                )
                                st.plotly_chart(fig, use_container_width=True, key=f"chart_plotly_{d_key}")
                else:
                    st.info("条件に一致するデータがありません。")
            else:
                st.info("対局データがまだありません。")

        elif st.session_state['active_page'] == "👥 グループ":
            with st.expander("➕ 新規グループ（セット）作成"):
                new_g_name = st.text_input("グループ名")
                # 全ユーザーからメンバーを選択
                all_users = pd.read_sql('SELECT username FROM users', sqlite3.connect(DB_NAME))['username'].tolist()
                selected_members = st.multiselect("メンバーを選択", all_users, default=[st.session_state['user']])
                
                # --- 追加：ルール選択 ---
                rule_options = ["連盟公式", "Mリーグ", "一般(競技)", "3麻標準"]
                selected_rule = st.selectbox("デフォルトルール", rule_options)
                
                # --- 修正後の保存処理 ---
                if st.button("作成"):
                    # 1. 自分のアカウントが選択されているかチェック
                    current_user = st.session_state['user']
                    
                    if not new_g_name:
                        st.error("グループ名を入力してください")
                    elif not selected_members:
                        st.error("メンバーを選択してください")
                    elif current_user not in selected_members:
                        # ここで自分が入っていない場合にエラーを出す
                        st.error(f"作成者自身（{current_user}）をメンバーに含める必要があります")
                    else:
                        # 2. 全てのチェックが通ればDBに保存
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute('INSERT OR REPLACE INTO groups (group_name, members, default_rule) VALUES (?, ?, ?)',
                                        (new_g_name, ",".join(selected_members), selected_rule))
                            conn.commit()
                        st.success(f"グループ「{new_g_name}」を作成しました！")
                        st.rerun()
            
            st.subheader("グループ一覧")
            # 自分がメンバーに含まれているグループのみをDBから取得
            current_user = st.session_state['user']
            with sqlite3.connect(DB_NAME) as conn:
                query = "SELECT * FROM groups WHERE members LIKE ?"
                g_df_db = pd.read_sql(query, conn, params=(f'%{current_user}%',))
            # ... (DBから g_df_db を取得する処理の後)
            
            # --- 修正後のループ内処理 (詳細設定ボタン追加版) ---

            for index, row in g_df_db.iterrows():
                with st.container():
                    # グループ名とルールの表示
                    st.markdown(f"### {row['group_name']}")
                    rule_display = row['default_rule'] if 'default_rule' in row and row['default_rule'] else "未設定"
                    st.info(f"設定ルール: {rule_display} / メンバー: {row['members']}")
                    
                    # ボタン配置用のカラム設定 (開始 / 詳細設定 / 削除)
                    col_start, col_edit, col_del = st.columns([2, 2, 1])
                    
                    with col_start:
                        if st.button("このセットを開始", key=f"start_{row['group_name']}", use_container_width=True):
                            st.session_state['active_page'] = "🎮 対局入力"
                            st.session_state['selected_group_from_manage'] = row['group_name']
                            rule_val = row['default_rule'] if 'default_rule' in row and row['default_rule'] else "連盟公式"
                            st.session_state['selected_rule_from_manage'] = rule_val
                            st.rerun()

                    with col_edit:
                        # 詳細設定ボタン（クリックで編集用フォームを展開）
                        show_edit = st.toggle("詳細設定", key=f"toggle_{row['group_name']}")

                    with col_del:
                        if st.button("🗑️", key=f"del_{row['group_name']}", use_container_width=True):
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute('DELETE FROM groups WHERE group_name=?', (row['group_name'],))
                                conn.commit()
                            st.success(f"削除しました")
                            st.rerun()

                    # 編集フォームの表示 (toggleがONの時のみ)
                    if show_edit:
                        with st.form(key=f"edit_form_{row['group_name']}"):
                            st.write("🔧 グループ情報の修正")
                            edit_name = st.text_input("グループ名", value=row['group_name'])
                            
                            # 全ユーザーからメンバーを選択
                            with sqlite3.connect(DB_NAME) as conn:
                                all_u = pd.read_sql('SELECT username FROM users', conn)['username'].tolist()
                            current_m = row['members'].split(',')
                            edit_m = st.multiselect("メンバー", all_u, default=current_m)
                            
                            edit_r = st.selectbox("ルール変更", ["連盟公式", "Mリーグ", "一般(競技)", "3麻標準"], 
                                                index=["連盟公式", "Mリーグ", "一般(競技)", "3麻標準"].index(rule_display) if rule_display in ["連盟公式", "Mリーグ", "一般(競技)", "3麻標準"] else 0)
                            
                            if st.form_submit_button("設定を更新"):
                                if edit_name and edit_m:
                                    with sqlite3.connect(DB_NAME) as conn:
                                        # 既存のレコードを削除して新しい名前で登録（名前変更対応）
                                        conn.execute('DELETE FROM groups WHERE group_name=?', (row['group_name'],))
                                        conn.execute('INSERT INTO groups (group_name, members, default_rule) VALUES (?, ?, ?)',
                                                    (edit_name, ",".join(edit_m), edit_r))
                                        conn.commit()
                                    st.success("更新しました！")
                                    st.rerun()
                                else:
                                    st.error("グループ名とメンバーは必須です")

                st.divider()
                
        elif st.session_state['active_page'] == "🤝 フレンド":
            st.header("🤝 フレンド機能")
            tab1, tab2, tab3, tab4 = st.tabs(["🔍 ユーザー検索", "📩 届いた申請", "📜 フレンド一覧", "💬 チャット"])

            with tab1:
                st.subheader("ユーザーを探す")
                search_q = st.text_input("ニックネームまたは本名で検索")
                if search_q:
                    with sqlite3.connect(DB_NAME) as conn:
                        # 自分以外を検索
                        users = pd.read_sql(
                            "SELECT username, real_name FROM users WHERE (username LIKE ? OR real_name LIKE ?) AND username != ?", 
                            conn, params=(f'%{search_q}%', f'%{search_q}%', st.session_state['user'])
                        )
                    for _, u in users.iterrows():
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"**{u['username']}** ({u['real_name']})")
                        if c2.button("申請", key=f"req_{u['username']}"):
                            with sqlite3.connect(DB_NAME) as conn:
                                # 既存の申請がないかチェックして保存
                                check = conn.execute("SELECT 1 FROM friends WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)", 
                                                (st.session_state['user'], u['username'], u['username'], st.session_state['user'])).fetchone()
                                if not check:
                                    conn.execute("INSERT INTO friends (sender, receiver, status) VALUES (?, ?, 'pending')", 
                                            (st.session_state['user'], u['username']))
                                    st.success("申請を送りました")
                                else: st.warning("既に申請中またはフレンドです")

            with tab2:
                st.subheader("届いている承認待ち申請")
                with sqlite3.connect(DB_NAME) as conn:
                    reqs = pd.read_sql("SELECT sender FROM friends WHERE receiver=? AND status='pending'", 
                                    conn, params=(st.session_state['user'],))
                for r in reqs['sender']:
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**{r}** さんから申請が届いています")
                    if c2.button("承認", key=f"acc_{r}"):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("UPDATE friends SET status='accepted' WHERE sender=? AND receiver=?", (r, st.session_state['user']))
                        st.rerun()

            with tab3:
                st.subheader("フレンドの成績")
                with sqlite3.connect(DB_NAME) as conn:
                    # 相互認証済みのフレンドを取得
                    f_list = pd.read_sql(
                        "SELECT CASE WHEN sender = ? THEN receiver ELSE sender END as f_name FROM friends WHERE (sender=? OR receiver=?) AND status='accepted'",
                        conn, params=(st.session_state['user'], st.session_state['user'], st.session_state['user'])
                    )
                
                if f_list.empty:
                    st.info("フレンドはまだいません")
                else:
                    sel_f = st.selectbox("成績を見るフレンドを選択", f_list['f_name'].tolist())
                    if sel_f:
                        # --- 成績計算ロジック ---
                        with sqlite3.connect(DB_NAME) as conn:
                            df_m = pd.read_sql("SELECT * FROM matches", conn)
                        
                        # そのフレンドが含まれる対局をフィルタ
                        f_matches = df_m[df_m['players'].apply(lambda x: sel_f in x.split(','))].copy()
                        
                        if not f_matches.empty:
                            stats = []
                            for _, row in f_matches.iterrows():
                                p_list = row['players'].split(',')
                                pt_list = list(map(float, row['p_scores'].split(',')))
                                idx = p_list.index(sel_f)
                                # 着順計算
                                scores = list(map(int, row['scores'].split(',')))
                                rank = sorted(range(len(scores)), key=lambda k: scores[k], reverse=True).index(idx) + 1
                                stats.append({'pt': pt_list[idx], 'rank': rank})
                            
                            st_df = pd.DataFrame(stats)
                            total_hanchan = len(st_df)
                            avg_rank = st_df['rank'].mean()
                            top_rate = (len(st_df[st_df['rank'] == 1]) / total_hanchan) * 100
                            rentai_rate = (len(st_df[st_df['rank'] <= 2]) / total_hanchan) * 100
                            last_avoid = (len(st_df[st_df['rank'] < 4]) / total_hanchan) * 100
                            total_pt = st_df['pt'].sum()

                            # 表示
                            st.markdown(f"### {get_user_icon(sel_f)} {sel_f} のスタッツ", unsafe_allow_html=True)
                            m1, m2, m3 = st.columns(3)
                            m1.metric("平均着順", f"{avg_rank:.2f}位")
                            m2.metric("合計Pt", f"{total_pt:.1f}pt")
                            m3.metric("対局数", f"{total_hanchan}回")
                            
                            m4, m5, m6 = st.columns(3)
                            m4.metric("トップ率", f"{top_rate:.1f}%")
                            m5.metric("連対率", f"{rentai_rate:.1f}%")
                            m6.metric("ラス回避率", f"{last_avoid:.1f}%")
                        else:
                            st.warning("このユーザーの対局データがまだありません")
            with tab4:
                st.subheader("💬 フレンドDM")
                
                # 相互フレンドのリストを取得
                with sqlite3.connect(DB_NAME) as conn:
                    f_list = pd.read_sql(
                        "SELECT CASE WHEN sender = ? THEN receiver ELSE sender END as f_name FROM friends WHERE (sender=? OR receiver=?) AND status='accepted'",
                        conn, params=(st.session_state['user'], st.session_state['user'], st.session_state['user'])
                    )

                if f_list.empty:
                    st.info("チャットできるフレンドがいません")
                else:
                    # チャット相手の選択
                    target_user = st.selectbox("チャット相手を選択", f_list['f_name'].tolist(), key="chat_target")
                    
                    # --- メッセージ表示エリア ---
                    st.markdown("---")
                    chat_placeholder = st.empty() # リアルタイム更新用

                    with sqlite3.connect(DB_NAME) as conn:
                        msgs = pd.read_sql(
                            "SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY timestamp ASC",
                            conn, params=(st.session_state['user'], target_user, target_user, st.session_state['user'])
                        )

                    with chat_placeholder.container():
                        for _, m in msgs.iterrows():
                            is_me = m['sender'] == st.session_state['user']
                            align = "right" if is_me else "left"
                            bg_color = "#DCF8C6" if is_me else "#FFFFFF"
                            
                            # --- 1. ここから削除ボタン付きのレイアウト ---
                            if is_me:
                                # 自分のメッセージは、左側に削除ボタン、右側にメッセージ
                                del_col, msg_col = st.columns([1, 9])
                                with del_col:
                                    # ボタンを小さく表示。keyにメッセージのidを含めるのがポイント
                                    if st.button("🗑️", key=f"del_{m['timestamp']}_{m['sender']}"):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            # 内容と送信者と時間で特定して削除
                                            conn.execute("DELETE FROM messages WHERE sender=? AND timestamp=? AND content=?", 
                                                        (m['sender'], m['timestamp'], m['content']))
                                        st.rerun()
                                with msg_col:
                                    content_html = f"<div style='background:{bg_color}; padding:10px; border-radius:10px; margin:5px; display:inline-block; max-width:100%;'>"
                                    content_html += f"<b>{m['sender']}</b><br>{m['content']}"
                                    if m['image_data']:
                                        content_html += f"<br><img src='{m['image_data']}' style='max-width:100%; border-radius:5px; margin-top:5px;'>"
                                    content_html += f"<br><small style='color:gray;'>{m['timestamp']}</small></div>"
                                    st.markdown(f"<div style='text-align:{align};'>{content_html}</div>", unsafe_allow_html=True)
                            else:
                                # 相手のメッセージは今まで通り（削除ボタンなし）
                                content_html = f"<div style='background:{bg_color}; padding:10px; border-radius:10px; margin:5px; display:inline-block; max-width:70%;'>"
                                content_html += f"<b>{m['sender']}</b><br>{m['content']}"
                                if m['image_data']:
                                    content_html += f"<br><img src='{m['image_data']}' style='max-width:100%; border-radius:5px; margin-top:5px;'>"
                                content_html += f"<br><small style='color:gray;'>{m['timestamp']}</small></div>"
                                st.markdown(f"<div style='text-align:{align};'>{content_html}</div>", unsafe_allow_html=True)

                    # --- 送信フォーム ---
                    st.markdown("---")
                    with st.form(key="chat_input", clear_on_submit=True):
                        col1, col2 = st.columns([4, 1])
                        msg_text = col1.text_input("メッセージを入力", placeholder="送信するメッセージ...")
                        uploaded_img = col2.file_uploader("📷", type=['png', 'jpg', 'jpeg'], label_visibility="collapsed")
                        submit = st.form_submit_button("送信")

                        if submit and (msg_text or uploaded_img):
                            img_base64 = None
                            if uploaded_img:
                                img_base64 = f"data:image/png;base64,{base64.b64encode(uploaded_img.read()).decode()}"
                            
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("INSERT INTO messages (sender, receiver, content, image_data) VALUES (?, ?, ?, ?)",
                                            (st.session_state['user'], target_user, msg_text, img_base64))
                            st.rerun()
                            



import time

def loading_screen(message="保存中..."):
    """麻雀牌がくるくる回るローディング画面を表示"""
    placeholder = st.empty()
    with placeholder.container():
        # CSSで回転アニメーションを定義
        st.markdown(
            """
            <style>
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .mahjong-loader {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 300px;
            }
            .tile {
                font-size: 80px;
                animation: spin 2s linear infinite;
            }
            </style>
            <div class="mahjong-loader">
                <div class="tile">🀄</div>
                <h3 style="margin-top: 20px;">""" + message + """</h3>
            </div>
            """,
            unsafe_allow_html=True
        )
        time.sleep(1.5) # 1.5秒間表示させる
    placeholder.empty() # 終わったら消去




if __name__ == '__main__':
    main()

