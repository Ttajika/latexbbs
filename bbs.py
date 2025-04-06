import streamlit as st
import psycopg2
import re
import os

# === DB接続 ===
def get_connection():
    return psycopg2.connect(
        dbname=os.environ["dbname"],
        user=os.environ["user"],
        password=os.environ["password"],
        host=os.environ["host"],
        port=os.environ["port"]
    )

# === DB初期化 ===
def init_db():
    conn = get_connection()
    c = conn.cursor()

    # # 開発中だけ！一度テーブルを削除
    # c.execute("DROP TABLE IF EXISTS posts")
    # c.execute("DROP TABLE IF EXISTS threads")

    # 正しい構造で作成
    c.execute('''CREATE TABLE IF NOT EXISTS threads (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    thread_id INTEGER REFERENCES threads(id),
                    author TEXT,
                    content TEXT,
                    parent_id INTEGER REFERENCES posts(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()


# === LaTeXレンダリング
def render_content(content):
    parts = re.split(r'(\$\$.*?\$\$)', content, flags=re.DOTALL)
    for part in parts:
        if part.startswith('$$') and part.endswith('$$'):
            st.latex(part.strip('$'))
        else:
            st.markdown(part, unsafe_allow_html=True)

# === 投稿の再帰表示
def render_posts(conn, thread_id, parent_id=None, level=0):
    c = conn.cursor()
    if parent_id is None:
        c.execute("SELECT id, author, content, created_at FROM posts WHERE thread_id=%s AND parent_id IS NULL ORDER BY created_at", (thread_id,))
    else:
        c.execute("SELECT id, author, content, created_at FROM posts WHERE thread_id=%s AND parent_id=%s ORDER BY created_at", (thread_id, parent_id))

    posts = c.fetchall()
    for pid, author, content, created in posts:
        indent = "&nbsp;" * (level * 4)
        st.markdown(f"{indent}**{author}**（{created}）:")
        render_content(content)

        with st.expander(f"{indent}🔁 この投稿に返信", expanded=False):
            reply_author = st.text_input(f"名前（返信ID {pid}）", "匿名", key=f"author_{pid}")
            reply_content = st.text_area(f"返信内容（投稿ID {pid}）", height=100, key=f"reply_{pid}")
            if st.button("返信する", key=f"reply_btn_{pid}"):
                if reply_content.strip():
                    c.execute("INSERT INTO posts (thread_id, author, content, parent_id) VALUES (%s, %s, %s, %s)",
                              (thread_id, reply_author, reply_content, pid))
                    conn.commit()
                    st.success("返信を投稿しました！")
                    st.rerun()

        render_posts(conn, thread_id, parent_id=pid, level=level+1)

# === アプリ開始 ===
init_db()
st.set_page_config(page_title="LaTeX掲示板", layout="wide")

conn = get_connection()
c = conn.cursor()

query_params = st.query_params
tid = query_params.get("tid", [None])[0]
url_mode = query_params.get("mode", [None])[0]

# サイドバーの選択と同期
if url_mode:
    mode = url_mode
else:
    mode = st.sidebar.radio("📋 メニュー", ["スレッド一覧", "新規スレッド", "スレッドを見る"])

# === スレッド一覧 ===
if mode == "スレッド一覧":
    st.title("📚 スレッド一覧")
    c.execute("SELECT id, title FROM threads ORDER BY created_at DESC")
    threads = c.fetchall()
    for tid, title in threads:
        # リンククリックで query_params をセット
        if st.button(f"📌 {title}", key=f"thread_btn_{tid}"):
            st.query_params(mode="スレッドを見る", tid=str(tid))
            st.rerun()


# === 新規スレッド作成 ===
elif mode == "新規スレッド":
    st.title("📝 新しいスレッドを作成")
    title = st.text_input("スレッドタイトル")
    if st.button("作成する") and title.strip():
        c.execute("INSERT INTO threads (title) VALUES (%s)", (title,))
        conn.commit()
        st.success("スレッドを作成しました")

# === スレッド閲覧 & 投稿 ===
elif mode == "スレッドを見る":
    query_params = st.query_params
    tid = query_params.get("tid", [None])[0]
    if tid:
        c.execute("SELECT title FROM threads WHERE id=%s", (tid,))
        row = c.fetchone()
        if row:
            st.title(f"📌 スレッド: {row[0]}")
            render_posts(conn, thread_id=tid)

            st.markdown("---")
            st.subheader("✍️ 新しい投稿")
            author = st.text_input("名前", "匿名", key="new_author")
            content = st.text_area("本文（LaTeX対応: $x^2$ または $$E=mc^2$$）", height=150, key="new_post")

            st.markdown("#### 🔍 プレビュー")
            if content.strip():
                render_content(content)
            else:
                st.info("本文に何か書くとプレビューされます。")

            if st.button("投稿する", key="submit_new_post"):
                if content.strip():
                    c.execute("INSERT INTO posts (thread_id, author, content, parent_id) VALUES (%s, %s, %s, NULL)",
                              (tid, author, content))
                    conn.commit()
                    st.success("投稿しました！")
                    st.rerun()
        else:
            st.error("スレッドが見つかりませんでした。")
    else:
        st.warning("スレッドIDが指定されていません。")
