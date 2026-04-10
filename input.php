<?php
declare(strict_types=1);
session_start();

if (empty($_SESSION['sungjuk_csrf'])) {
    $_SESSION['sungjuk_csrf'] = bin2hex(random_bytes(24));
}

$token = $_SESSION['sungjuk_csrf'];
$flash = $_SESSION['sungjuk_flash'] ?? null;
unset($_SESSION['sungjuk_flash']);
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>성적 입력</title>
    <style>
        :root{
            --bg:#f3f6ff;--card:#fff;--text:#0f172a;--muted:#64748b;
            --line:#dbe5f4;--primary:#2563eb;--primary-dark:#1d4ed8;
            --shadow:0 14px 34px rgba(15,23,42,.10)
        }
        *{box-sizing:border-box}
        body{
            margin:0;min-height:100vh;padding:24px;
            background:linear-gradient(145deg,#eaf0ff 0%,var(--bg) 50%,#e0f2fe 100%);
            color:var(--text);font-family:"Noto Sans KR",Arial,sans-serif
        }
        .wrap{max-width:860px;margin:0 auto}
        .card{
            background:var(--card);border:1px solid var(--line);border-radius:18px;
            box-shadow:var(--shadow);padding:24px
        }
        h1{margin:0 0 8px;font-size:30px}
        .muted{margin:0 0 18px;color:var(--muted)}
        .flash{
            padding:10px 12px;border-radius:10px;margin-bottom:14px;
            border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;font-weight:700
        }
        .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
        .full{grid-column:1/-1}
        label{display:block;font-weight:700;font-size:14px}
        input{
            width:100%;margin-top:6px;padding:11px 12px;border:1px solid #cfd8e6;
            border-radius:10px;font-size:15px;outline:none
        }
        input:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgba(37,99,235,.15)}
        .actions{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap}
        button,a.btn{
            border:0;border-radius:10px;padding:10px 14px;font-size:14px;
            font-weight:700;text-decoration:none;display:inline-flex;align-items:center
        }
        button{background:var(--primary);color:#fff;cursor:pointer}
        button:hover{background:var(--primary-dark)}
        a.btn{background:#eef2ff;color:#1e3a8a;border:1px solid #dbeafe}
        @media(max-width:700px){.grid{grid-template-columns:1fr}}
    </style>
</head>
<body>
<div class="wrap">
    <section class="card">
        <h1>성적 입력</h1>
        <p class="muted">학번/출석/과제/중간/기말 점수를 입력하면 합계와 평점을 계산하고 저장합니다.</p>

        <?php if ($flash): ?>
            <div class="flash"><?= htmlspecialchars((string)$flash, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>

        <form method="post" action="sungjuk_proc_new.php">
            <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($token, ENT_QUOTES, 'UTF-8') ?>">
            <div class="grid">
                <label class="full">학번
                    <input type="text" name="student_id" maxlength="20" required placeholder="예: 20260001">
                </label>
                <label>출석 (0~100)
                    <input type="number" name="att" min="0" max="100" required>
                </label>
                <label>과제 (0~100)
                    <input type="number" name="hw" min="0" max="100" required>
                </label>
                <label>중간 (0~100)
                    <input type="number" name="mid" min="0" max="100" required>
                </label>
                <label>기말 (0~100)
                    <input type="number" name="final" min="0" max="100" required>
                </label>
            </div>
            <div class="actions">
                <button type="submit">계산 후 저장</button>
                <a class="btn" href="sungjuk_list_new.php">성적 리스트 보기</a>
            </div>
        </form>
    </section>
</div>
</body>
</html>
