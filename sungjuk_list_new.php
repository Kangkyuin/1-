<?php
declare(strict_types=1);
session_start();

mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function grade_class(string $grade): string
{
    return match ($grade) {
        'A' => 'badge-a',
        'B' => 'badge-b',
        'C' => 'badge-c',
        'D' => 'badge-d',
        default => 'badge-f',
    };
}

try {
    $db = new mysqli('localhost', 'test', 'test1234', 'school');
    $db->set_charset('utf8mb4');

    $db->query(
        "CREATE TABLE IF NOT EXISTS sungjuk (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id VARCHAR(20) NOT NULL,
            att TINYINT UNSIGNED NOT NULL,
            hw TINYINT UNSIGNED NOT NULL,
            mid TINYINT UNSIGNED NOT NULL,
            final TINYINT UNSIGNED NOT NULL,
            total SMALLINT UNSIGNED NOT NULL,
            average_score DECIMAL(5,2) NOT NULL,
            grade CHAR(1) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    $stmt = $db->prepare(
        'SELECT id, student_id, att, hw, mid, final, total, average_score, grade, created_at
         FROM sungjuk
         ORDER BY id DESC'
    );
    $stmt->execute();
    $result = $stmt->get_result();
} catch (Throwable $e) {
    http_response_code(500);
    exit('목록 조회 중 오류가 발생했습니다.');
}
?>
<!doctype html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>성적 목록</title>
    <style>
        :root{
            --bg:#f1f5f9;--card:#fff;--line:#e2e8f0;--text:#0f172a;--muted:#64748b;--brand:#2563eb;
        }
        *{box-sizing:border-box}
        body{
            margin:0;
            font-family:Inter,"Noto Sans KR",Arial,sans-serif;
            background:radial-gradient(circle at 0% 0%,#dbeafe 0,#f8fafc 38%,var(--bg) 100%);
            color:var(--text);
            min-height:100vh;
            padding:32px 18px 60px;
        }
        .wrap{max-width:1200px;margin:0 auto}
        .card{
            background:var(--card);border:1px solid var(--line);border-radius:20px;overflow:hidden;
            box-shadow:0 24px 60px rgba(2,6,23,.08);
        }
        .top{
            display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;
            padding:24px 28px;border-bottom:1px solid var(--line);
        }
        h1{margin:0;font-size:26px}
        .meta{margin-top:6px;color:var(--muted);font-size:14px}
        .btn{
            display:inline-flex;align-items:center;justify-content:center;
            text-decoration:none;font-weight:700;border-radius:10px;padding:10px 14px;
            border:1px solid #bfdbfe;background:#dbeafe;color:#1d4ed8
        }
        .btn-primary{background:var(--brand);border-color:var(--brand);color:#fff}
        .table-wrap{padding:20px;overflow-x:auto}
        table{width:100%;min-width:980px;border-collapse:separate;border-spacing:0}
        th,td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}
        th{background:#f8fafc;color:#334155;font-size:13px;text-transform:uppercase;letter-spacing:.02em}
        tbody tr:hover{background:#f8fbff}
        .badge{
            display:inline-flex;align-items:center;justify-content:center;border-radius:999px;
            min-width:28px;padding:3px 8px;font-weight:800;font-size:12px
        }
        .badge-a{background:#dcfce7;color:#166534}
        .badge-b{background:#dbeafe;color:#1d4ed8}
        .badge-c{background:#fef9c3;color:#854d0e}
        .badge-d{background:#ffedd5;color:#9a3412}
        .badge-f{background:#fee2e2;color:#991b1b}
        .empty{color:var(--muted);padding:34px 8px}
    </style>
</head>
<body>
<div class="wrap">
    <section class="card">
        <div class="top">
            <div>
                <h1>SungJuk 테이블 목록</h1>
                <p class="meta">총 <?= (int)$result->num_rows ?>건</p>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <a class="btn btn-primary" href="input.php">+ 성적 입력</a>
                <a class="btn" href="sungjuk_list_new.php">새로고침</a>
            </div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                <tr>
                    <th>ID</th>
                    <th>학번</th>
                    <th>출석</th>
                    <th>과제</th>
                    <th>중간</th>
                    <th>기말</th>
                    <th>합계</th>
                    <th>평균</th>
                    <th>평점</th>
                    <th>저장일시</th>
                </tr>
                </thead>
                <tbody>
                <?php if ($result->num_rows === 0): ?>
                    <tr><td class="empty" colspan="10">저장된 데이터가 없습니다.</td></tr>
                <?php else: ?>
                    <?php while ($row = $result->fetch_assoc()): ?>
                        <tr>
                            <td><?= (int)$row['id'] ?></td>
                            <td><?= h((string)$row['student_id']) ?></td>
                            <td><?= (int)$row['att'] ?></td>
                            <td><?= (int)$row['hw'] ?></td>
                            <td><?= (int)$row['mid'] ?></td>
                            <td><?= (int)$row['final'] ?></td>
                            <td><strong><?= (int)$row['total'] ?></strong></td>
                            <td><?= number_format((float)$row['average_score'], 2) ?></td>
                            <td><span class="badge <?= grade_class((string)$row['grade']) ?>"><?= h((string)$row['grade']) ?></span></td>
                            <td><?= h((string)$row['created_at']) ?></td>
                        </tr>
                    <?php endwhile; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </section>
</div>
</body>
</html>
<?php
$stmt->close();
$db->close();
?>
