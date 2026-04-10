<?php
declare(strict_types=1);
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>게시글 작성하기</title>
    <style>
        :root {
            --bg: #f7f8fc;
            --card: #ffffff;
            --primary: #3f6efc;
            --primary-dark: #3358c9;
            --text: #212529;
            --muted: #6c757d;
            --border: #e5e7eb;
            --shadow: 0 12px 30px rgba(16, 24, 40, 0.08);
        }

        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 28px;
            font-family: "Noto Sans KR", Arial, sans-serif;
            background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 100%);
            color: var(--text);
        }

        .wrapper {
            max-width: 860px;
            margin: 0 auto;
        }

        .card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: var(--shadow);
            padding: 28px;
        }

        h2 {
            margin: 0 0 6px;
            font-size: 28px;
        }

        .desc {
            margin: 0 0 22px;
            color: var(--muted);
        }

        .field {
            margin-bottom: 16px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 700;
        }

        input[type="text"],
        textarea {
            width: 100%;
            border: 1px solid #d0d5dd;
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 15px;
            transition: border-color 0.2s, box-shadow 0.2s;
            background: #fff;
        }

        input[type="text"]:focus,
        textarea:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 4px rgba(63, 110, 252, 0.15);
            outline: none;
        }

        textarea {
            min-height: 190px;
            resize: vertical;
        }

        .actions {
            display: flex;
            gap: 10px;
            margin-top: 8px;
            flex-wrap: wrap;
        }

        button,
        .btn-link {
            border: 0;
            border-radius: 12px;
            padding: 11px 16px;
            font-size: 15px;
            text-decoration: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .btn-submit {
            background: var(--primary);
            color: #fff;
            font-weight: 700;
        }

        .btn-submit:hover {
            background: var(--primary-dark);
        }

        .btn-link {
            background: #eef2ff;
            color: #1f3aa8;
            border: 1px solid #d8e0ff;
        }

        .hint {
            margin-top: 10px;
            color: var(--muted);
            font-size: 13px;
        }
    </style>
</head>
<body>
<div class="wrapper">
    <div class="card">
        <h2>게시글 작성하기</h2>
        <p class="desc">작성자, 제목, 본문을 입력한 후 저장하면 Message 테이블에 등록됩니다.</p>

        <form name="board" method="post" action="board_proc.php">
            <div class="field">
                <label for="muname">작성자</label>
                <input id="muname" type="text" name="muname" maxlength="30" required placeholder="예: 홍길동">
            </div>

            <div class="field">
                <label for="msubject">제목</label>
                <input id="msubject" type="text" name="msubject" maxlength="120" required placeholder="제목을 입력하세요">
            </div>

            <div class="field">
                <label for="mcontent">본문</label>
                <textarea id="mcontent" name="mcontent" required placeholder="내용을 입력하세요"></textarea>
            </div>

            <div class="actions">
                <button class="btn-submit" type="submit">저장</button>
                <a class="btn-link" href="board_list.php">목록 보기</a>
                <a class="btn-link" href="db_test.php">DB 테스트</a>
            </div>
            <p class="hint">빈 값은 저장되지 않도록 서버에서 한 번 더 검증합니다.</p>
        </form>
    </div>
</div>
</body>
</html>
