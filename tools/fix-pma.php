<?php
// Used by fix-pma.sh. Reads phpMyAdmin's control user from config.inc.php so the
// password never appears on a command line. fix-pma.sh runs this as the config's
// owner (daemon), never as root, and feeds it on stdin:
//   php -- sql   <config.inc.php> < fix-pma.php   print SQL that creates/updates the account
//   php -- check <config.inc.php> < fix-pma.php   try to log in as the control user

const PMADB = 'phpmyadmin'; // the database phpMyAdmin's sql/create_tables.sql creates

if ($argc !== 3 || !in_array($argv[1], ['sql', 'check'], true) || !is_file($argv[2])) {
    fwrite(STDERR, "usage: php -- sql|check <config.inc.php> < fix-pma.php\n");
    exit(2);
}

// Anything the config prints (warnings, text after its closing tag) must not end up in the SQL.
ob_start();
include $argv[2];
ob_end_clean();

$server = $cfg['Servers'][1] ?? [];
$user = (string)($server['controluser'] ?? '');
$pass = (string)($server['controlpass'] ?? '');
$db = (string)($server['pmadb'] ?? '');

if ($user === '' || $pass === '') {
    fwrite(STDERR, "controluser/controlpass not set in {$argv[2]}\n");
    exit(1);
}
if ($db !== PMADB) {
    fwrite(STDERR, "pmadb is '$db', but this fix only sets up '" . PMADB . "'\n");
    exit(1);
}
if (str_contains($user . $pass, "\0")) {
    fwrite(STDERR, "controluser/controlpass contains a NUL byte\n");
    exit(1);
}

if ($argv[1] === 'check') {
    // Connect the way phpMyAdmin does: controlhost/controlport, else the server's host/port.
    $host = (string)($server['controlhost'] ?? '') ?: (string)($server['host'] ?? '') ?: 'localhost';
    $port = (int)(($server['controlport'] ?? '') ?: ($server['port'] ?? '') ?: 0);
    $socket = (string)($server['socket'] ?? '') ?: null;
    mysqli_report(MYSQLI_REPORT_OFF);
    $conn = @new mysqli($host, $user, $pass, $db, $port ?: null, $socket);
    if ($conn->connect_errno) {
        echo "FAILED: {$conn->connect_error}\n";
        exit(1);
    }
    echo "OK: $user can log in. Reload phpMyAdmin.\n";
    exit(0);
}

// '' for quotes works in every sql_mode; switching NO_BACKSLASH_ESCAPES off first makes
// the escaped backslashes mean the same thing whatever the server default is.
$str = fn(string $v): string => "'" . str_replace(['\\', "'"], ['\\\\', "''"], $v) . "'";
$account = $str($user) . "@'localhost'";

echo "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');\n";
echo "CREATE USER IF NOT EXISTS $account;\n";
echo "ALTER USER $account IDENTIFIED BY " . $str($pass) . ";\n";
echo "GRANT SELECT, INSERT, UPDATE, DELETE ON `" . PMADB . "`.* TO $account;\n";
