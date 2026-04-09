<h2>폼에 입력한 성적 저장하기</h2><hr>
<?php
$db_con = mysqli_connect("localhost", "test", "test1234", "school");
if (!$db_con) exit("DB 연결 실패");

$create_sql = "CREATE TABLE IF NOT EXISTS sungjuk (
id INT AUTO_INCREMENT PRIMARY KEY,
student_id VARCHAR(20) NOT NULL,
att INT NOT NULL,
hw INT NOT NULL,
mid INT NOT NULL,
final INT NOT NULL,
total INT NOT NULL,
grade VARCHAR(2) NOT NULL
)";
mysqli_query($db_con, $create_sql);

if (!isset($_POST["student_id"])) {
?>
<form method="post" action="sungjuk_proc.php">
학번 : <input type="text" name="student_id"><br><br>
출석 : <input type="number" name="att"><br><br>
과제 : <input type="number" name="hw"><br><br>
중간 : <input type="number" name="mid"><br><br>
기말 : <input type="number" name="final"><br><br>
<input type="submit" value="계산 후 저장">
</form>
<br>
<a href="sungjuk_list.php"><button type="button">성적 리스트 보기</button></a>
<?php
    mysqli_close($db_con);
    exit;
}

$student_id = $_POST["student_id"];
$att = (int)$_POST["att"];
$hw = (int)$_POST["hw"];
$mid = (int)$_POST["mid"];
$final = (int)$_POST["final"];

$total = $att + $hw + $mid + $final;
if ($total >= 90) $grade = "A";
else if ($total >= 80) $grade = "B";
else if ($total >= 70) $grade = "C";
else if ($total >= 60) $grade = "D";
else $grade = "F";

$sql = "INSERT INTO sungjuk (student_id, att, hw, mid, final, total, grade) VALUES (?, ?, ?, ?, ?, ?, ?)";
$stmt = $db_con->prepare($sql);
$stmt->bind_param("siiiiis", $student_id, $att, $hw, $mid, $final, $total, $grade);
$stmt->execute();

echo "<p>학번 : " . $student_id;
echo "<p>합계 : " . $total;
echo "<p>평점 : " . $grade . "<hr>";
if ($stmt->affected_rows) echo "<p>성적 저장 성공 (OK)";
else echo "<p>성적 저장 실패 (Fail)";
?>
<br>
<a href="sungjuk_list.php"><button type="button">성적 리스트 보기</button></a>
<a href="sungjuk_proc.php"><button type="button">다시 입력</button></a>
<?php
$stmt->close();
mysqli_close($db_con);
?>
