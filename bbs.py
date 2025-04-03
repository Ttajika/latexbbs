import streamlit as st
import psycopg2
import re
import os

# === DB接続 ===
def get_connection():
    return psycopg2.connect(
        dbname=st.secrets["dbname"],
        user=st.secrets["user"],
        password=st.secrets["password"],
        host=st.secrets["host"],
        port=st.secrets["port"]
    )


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY,
                    thread_id INTEGER,
                    author TEXT,
                    content TEXT,
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(thread_id) REFERENCES threads(id),
                    FOREIGN KEY(parent_id) REFERENCES posts(id)
                )''')
    conn.commit()
    conn.close()

# === LaTeXレンダリング（$$...$$をst.latex、その他はmarkdown）
def render_content(content):
    parts = re.split(r'(\$\$.*?\$\$)', content, flags=re.DOTALL)
    for part in parts:
        if part.startswith('$$') and part.endswith('$$'):
            st.latex(part.strip('$'))
        else:
            st.markdown(part, unsafe_allow_html=True)

# === 投稿の再帰表示 ===
def render_posts(conn, thread_id, parent_id=None, level=0):
    c = conn.cursor()
    if parent_id is None:
        c.execute("SELECT id, author, content, created_at FROM posts WHERE thread_id=? AND parent_id IS NULL ORDER BY created_at", (thread_id,))
    else:
        c.execute("SELECT id, author, content, created_at FROM posts WHERE thread_id=? AND parent_id=? ORDER BY created_at", (thread_id, parent_id))

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
                    c.execute("INSERT INTO posts (thread_id, author, content, parent_id) VALUES (?, ?, ?, ?)",
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

mode = st.sidebar.radio("📋 メニュー", ["スレッド一覧", "新規スレッド", "スレッドを見る"])

# === スレッド一覧 ===
if mode == "スレッド一覧":
    st.title("📚 スレッド一覧")
    c.execute("SELECT id, title FROM threads ORDER BY created_at DESC")
    threads = c.fetchall()
    for tid, title in threads:
        st.markdown(f"### [{title}](?mode=スレッドを見る&tid={tid})")

# === 新規スレッド作成 ===
elif mode == "新規スレッド":
    st.title("📝 新しいスレッドを作成")
    title = st.text_input("スレッドタイトル")
    if st.button("作成する") and title.strip():
        c.execute("INSERT INTO threads (title) VALUES (?)", (title,))
        conn.commit()
        st.success("スレッドを作成しました")

# === スレッド閲覧 & 投稿 ===
elif mode == "スレッドを見る":
    query_params = st.query_params
    tid = query_params.get("tid", [None])[0]
    if tid:
        c.execute("SELECT title FROM threads WHERE id=?", (tid,))
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
                    c.execute("INSERT INTO posts (thread_id, author, content, parent_id) VALUES (?, ?, ?, NULL)",
                              (tid, author, content))
                    conn.commit()
                    st.success("投稿しました！")
                    st.rerun()
        else:
            st.error("スレッドが見つかりませんでした。")
    else:
        st.warning("スレッドIDが指定されていません。")
