<?php
declare(strict_types=1);

function db_connect(): mysqli
{
    $db = new mysqli('localhost', 'test', 'test1234', 'testdb');
    if ($db->connect_errno) {
        http_response_code(500);
        exit('DB 연결 실패: ' . htmlspecialchars($db->connect_error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'));
    }
    $db->set_charset('utf8mb4');
    return $db;
}

function ensure_message_table(mysqli $db): void
{
    $sql = <<<SQL
CREATE TABLE IF NOT EXISTS Message (
    MID INT AUTO_INCREMENT PRIMARY KEY,
    MSubject VARCHAR(200) NOT NULL,
    MContent TEXT NOT NULL,
    MUName VARCHAR(60) NOT NULL,
    MNalzza DATE NOT NULL
)
SQL;

    if (!$db->query($sql)) {
        http_response_code(500);
        exit('Message 테이블 준비 실패: ' . htmlspecialchars($db->error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'));
    }
}

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: board_ip.php');
    exit;
}

$muname = trim((string)($_POST['muname'] ?? ''));
$msubject = trim((string)($_POST['msubject'] ?? ''));
$mcontent = trim((string)($_POST['mcontent'] ?? ''));
$mdate = date('Y-m-d');

if ($muname === '' || $msubject === '' || $mcontent === '') {
    exit('작성자, 제목, 본문을 모두 입력하세요.');
}

$mysqli = db_connect();
ensure_message_table($mysqli);
$sql = 'INSERT INTO Message (MSubject, MContent, MUName, MNalzza) VALUES (?, ?, ?, ?)';
$stmt = $mysqli->prepare($sql);

if (!$stmt) {
    $mysqli->close();
    http_response_code(500);
    exit('SQL 준비 실패: ' . h($mysqli->error));
}

$stmt->bind_param('ssss', $msubject, $mcontent, $muname, $mdate);
$ok = $stmt->execute();
$affectedRows = $stmt->affected_rows;
$stmt->close();
$mysqli->close();
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>게시글 저장 결과</title>
    <style>
        :root {
            --bg: #0b1020;
            --card: #111933;
            --text: #e8eeff;
            --muted: #9fb0df;
            --ok: #3ad29f;
            --fail: #ff6b7f;
            --accent: #6ea8ff;
            --border: #2a3766;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Noto Sans KR", Arial, sans-serif;
            background: radial-gradient(circle at 20% 10%, #15224e 0%, var(--bg) 55%);
            color: var(--text);
            display: grid;
            place-items: center;
            padding: 24px;
        }
        .card {
            width: min(780px, 100%);
            background: linear-gradient(180deg, rgba(255,255,255,0.04), transparent), var(--card);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 24px 60px rgba(0,0,0,0.35);
        }
        h2 {
            margin: 0 0 8px 0;
            font-size: 28px;
        }
        hr {
            border: none;
            border-top: 1px solid var(--border);
            margin: 10px 0 18px;
        }
        .grid {
            display: grid;
            grid-template-columns: 120px 1fr;
            gap: 10px 12px;
            margin-bottom: 18px;
        }
        .k { color: var(--muted); }
        .v { color: var(--text); }
        .content-box {
            white-space: pre-wrap;
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            margin-top: 6px;
        }
        .status {
            margin: 16px 0 4px;
            font-weight: 700;
        }
        .ok { color: var(--ok); }
        .fail { color: var(--fail); }
        .links {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 16px;
        }
        a.btn {
            text-decoration: none;
            color: #fff;
            background: var(--accent);
            padding: 10px 14px;
            border-radius: 10px;
            font-weight: 700;
            display: inline-block;
        }
        a.btn.secondary { background: #344880; }
    </style>
</head>
<body>
    <section class="card">
        <h2>폼에 입력한 게시글 저장하기</h2>
        <hr>
        <div class="grid">
            <div class="k">작성자</div><div class="v"><?= h($muname) ?> 님</div>
            <div class="k">제목</div><div class="v"><?= h($msubject) ?></div>
            <div class="k">날짜</div><div class="v"><?= h($mdate) ?></div>
            <div class="k">본문</div>
            <div class="v">
                <div class="content-box"><?= h($mcontent) ?></div>
            </div>
        </div>

        <?php if ($ok && $affectedRows > 0): ?>
            <p class="status ok">saving procedure is ok</p>
        <?php else: ?>
            <p class="status fail">saving procedure is fail</p>
        <?php endif; ?>

        <div class="links">
            <a class="btn" href="board_list.php">목록 보기</a>
            <a class="btn secondary" href="board_ip.php">다시 작성</a>
        </div>
    </section>
</body>
</html>
