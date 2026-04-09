<?php
$dbCon = mysqli_connect('localhost', 'test', 'test1234', 'testdb');
$isConnected = (bool)$dbCon;
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>db_test.php</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Pretendard", "Noto Sans KR", Arial, sans-serif;
            background: linear-gradient(135deg, #eef2ff, #f8fafc 45%, #ecfeff);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            color: #0f172a;
        }
        .card {
            width: 100%;
            max-width: 700px;
            background: #ffffff;
            border-radius: 20px;
            box-shadow: 0 20px 45px rgba(15, 23, 42, 0.14);
            padding: 30px;
        }
        h2 {
            margin: 0 0 10px;
            font-size: 30px;
        }
        hr {
            border: 0;
            border-top: 1px solid #e2e8f0;
            margin: 14px 0 22px;
        }
        .result {
            padding: 16px;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 700;
        }
        .ok {
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        .fail {
            background: #fef2f2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }
        .hint {
            margin-top: 12px;
            color: #475569;
            font-size: 14px;
        }
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }
        .actions a {
            text-decoration: none;
            color: #ffffff;
            background: #2563eb;
            padding: 10px 14px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 14px;
        }
        .actions a:nth-child(2) { background: #0f766e; }
        .actions a:nth-child(3) { background: #7c3aed; }
    </style>
</head>
<body>
    <div class="card">
        <h2>데이터베이스 연동 테스트</h2>
        <hr>
        <?php if ($isConnected): ?>
            <div class="result ok">연동 성공!!!!</div>
            <p class="hint">testdb 데이터베이스에 정상 접속되었습니다.</p>
        <?php else: ?>
            <div class="result fail">연동 실패~~~~~</div>
            <p class="hint">DB 계정/비밀번호/DB명 또는 MariaDB/MySQL 실행 상태를 확인하세요.</p>
        <?php endif; ?>
        <div class="actions">
            <a href="board_ip.php">게시글 작성하기</a>
            <a href="board_list.php">게시글 목록 보기</a>
            <a href="sungjuk_proc.php">성적 입력 페이지</a>
        </div>
    </div>
</body>
</html>
<?php
if ($dbCon) {
    mysqli_close($dbCon);
}
?>
