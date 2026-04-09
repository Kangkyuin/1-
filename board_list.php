<?php
declare(strict_types=1);

$dbHost = 'localhost';
$dbUser = 'test';
$dbPass = 'test1234';
$dbName = 'testdb';

$dbCon = mysqli_connect($dbHost, $dbUser, $dbPass, $dbName);
if (!$dbCon) {
    http_response_code(500);
    exit('DB 연결 실패: ' . mysqli_connect_error());
}
mysqli_set_charset($dbCon, 'utf8mb4');

$createSql = <<<SQL
CREATE TABLE IF NOT EXISTS Message (
    MID INT AUTO_INCREMENT PRIMARY KEY,
    MSubject VARCHAR(200) NOT NULL,
    MContent TEXT NOT NULL,
    MUName VARCHAR(60) NOT NULL,
    MNalzza DATE NOT NULL
)
SQL;
if (!mysqli_query($dbCon, $createSql)) {
    http_response_code(500);
    exit('테이블 생성 실패: ' . mysqli_error($dbCon));
}

$sql = 'SELECT MID, MUName, MSubject, MNalzza FROM Message ORDER BY MID DESC';
$result = mysqli_query($dbCon, $sql);
if (!$result) {
    http_response_code(500);
    exit('조회 실패: ' . mysqli_error($dbCon));
}
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>board_list.php</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Pretendard", "Noto Sans KR", Arial, sans-serif;
            background: linear-gradient(145deg, #eef2ff 0%, #f8fafc 40%, #dbeafe 100%);
            color: #0f172a;
            padding: 30px 16px 60px;
        }
        .wrap {
            max-width: 1060px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 24px;
            box-shadow: 0 24px 50px rgba(15, 23, 42, 0.10);
            backdrop-filter: blur(10px);
            overflow: hidden;
        }
        .top {
            padding: 28px 30px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
        }
        h2 {
            margin: 0;
            font-size: 28px;
        }
        .tools a {
            display: inline-block;
            text-decoration: none;
            color: #1d4ed8;
            background: #dbeafe;
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            padding: 10px 14px;
            font-weight: 700;
            margin-left: 8px;
        }
        .table-wrap {
            overflow-x: auto;
            padding: 24px 22px 28px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 720px;
        }
        th, td {
            border-bottom: 1px solid #e2e8f0;
            padding: 14px 12px;
            text-align: left;
        }
        th {
            background: #f8fafc;
            color: #334155;
            font-size: 14px;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        tbody tr:hover {
            background: #f8fbff;
        }
        .num {
            font-weight: 700;
            color: #0f172a;
        }
        .subject {
            font-weight: 700;
            color: #1e293b;
        }
        .empty {
            text-align: center;
            color: #64748b;
            padding: 40px 10px;
        }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <div class="top">
                <h2>Message 테이블 목록 보여주기</h2>
                <div class="tools">
                    <a href="board_ip.php">+ 새 글 쓰기</a>
                    <a href="db_test.php">DB 연동 테스트</a>
                </div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>일련번호</th>
                            <th>작성자</th>
                            <th>제목</th>
                            <th>날짜</th>
                        </tr>
                    </thead>
                    <tbody>
                    <?php if (mysqli_num_rows($result) === 0): ?>
                        <tr>
                            <td class="empty" colspan="4">아직 등록된 게시글이 없습니다.</td>
                        </tr>
                    <?php else: ?>
                        <?php while ($row = mysqli_fetch_assoc($result)): ?>
                            <tr>
                                <td class="num"><?= (int)$row['MID'] ?></td>
                                <td><?= htmlspecialchars((string)$row['MUName'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td class="subject"><?= htmlspecialchars((string)$row['MSubject'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string)$row['MNalzza'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            </tr>
                        <?php endwhile; ?>
                    <?php endif; ?>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
<?php mysqli_close($dbCon); ?>
