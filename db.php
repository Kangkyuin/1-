<?php
declare(strict_types=1);

// DB 접속 정보(환경에 맞게 수정)
$dbHost = '127.0.0.1';
$dbUser = 'root';
$dbPass = '';
$dbName = 'school';
$dbPort = 3306;

$mysqli = new mysqli($dbHost, $dbUser, $dbPass, $dbName, $dbPort);

if ($mysqli->connect_errno) {
    http_response_code(500);
    exit('DB 연결 실패: ' . $mysqli->connect_error);
}

$mysqli->set_charset('utf8mb4');

/**
 * 과제 실행 편의를 위해 테이블이 없으면 자동 생성합니다.
 */
function ensure_sungjuk_table(mysqli $mysqli): void
{
    $sql = <<<SQL
CREATE TABLE IF NOT EXISTS sungjuk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hakbun VARCHAR(20) NOT NULL,
    attendance INT NOT NULL,
    assignment_score INT NOT NULL,
    midterm_score INT NOT NULL,
    final_score INT NOT NULL,
    total_score INT NOT NULL,
    average_score DECIMAL(5,2) NOT NULL,
    grade VARCHAR(2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
SQL;

    if (!$mysqli->query($sql)) {
        http_response_code(500);
        exit('sungjuk 테이블 생성 실패: ' . $mysqli->error);
    }
}
