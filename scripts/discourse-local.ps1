# Windows alternative to discourse.sh, using a Linux source volume and one worker.
# PostgreSQL/Redis here belong only to the disposable Discourse test site.
param([ValidateSet('init', 'start', 'status', 'logs', 'stop')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
$Container = 'waata-discourse'
$Image = 'discourse/discourse_dev:20250930-0017'
$Revision = '3e7317b3344cca6c6510a32cc4c5c0f540132ad9'

function Invoke-DiscourseDocker {
    & docker.exe @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed ($LASTEXITCODE)" }
}

Push-Location $Repo
try {
    if ($Action -eq 'init') {
        & git submodule update --init --depth 1 testsites/discourse
        if ($LASTEXITCODE -ne 0) { throw 'Cannot initialize pinned Discourse submodule' }
        $ActualRevision = & git -C testsites/discourse rev-parse HEAD
        if ($ActualRevision -ne $Revision) { throw 'Discourse revision does not match the scenario baseline' }
        New-Item -ItemType Directory -Force -Path .local/discourse | Out-Null
        & docker container inspect $Container *> $null
        if ($LASTEXITCODE -ne 0) {
            Invoke-DiscourseDocker run -d --name $Container --hostname discourse `
                -p 127.0.0.1:4200:4200 -p 127.0.0.1:8025:8025 `
                --mount type=volume,source=waata-discourse-src,target=/src `
                --mount type=volume,source=waata-discourse-pg,target=/shared/postgres_data `
                --mount type=volume,source=waata-discourse-redis,target=/shared/redis `
                -e DISCOURSE_HOSTNAME=127.0.0.1 -e DISCOURSE_PORT=4200 `
                -e RAILS_DEVELOPMENT_HOSTS=127.0.0.1 -e PGUSER=discourse $Image /sbin/boot
        } else { Invoke-DiscourseDocker start $Container }
        # Do not overwrite an existing source volume or change the upstream submodule.
        & docker exec $Container test -f /src/bin/ember-cli
        if ($LASTEXITCODE -ne 0) {
            $Archive = Join-Path $Repo '.local/discourse/source.tar'
            & git -C testsites/discourse archive --format=tar "--output=$Archive" $Revision
            if ($LASTEXITCODE -ne 0) { throw 'Cannot archive pinned source' }
            Invoke-DiscourseDocker cp $Archive "${Container}:/tmp/waata-source.tar"
            Invoke-DiscourseDocker exec $Container tar -xf /tmp/waata-source.tar -C /src
        }
        Invoke-DiscourseDocker exec $Container chown -R discourse:discourse /src
        Invoke-DiscourseDocker exec -u discourse -w /src $Container sh -c "find bin -maxdepth 1 -type f -exec sed -i 's/\r$//' {} +"
        Invoke-DiscourseDocker exec -u discourse -w /src $Container bundle install
        Invoke-DiscourseDocker exec -u discourse -w /src $Container pnpm install --frozen-lockfile
        Invoke-DiscourseDocker exec -u discourse -w /src -e SKIP_MULTISITE=1 -e SKIP_TEST_DATABASE=1 $Container bin/rake db:create db:migrate
        Write-Output 'Create local fixture accounts next: uv run --locked python scripts/discourse-agent-check.py prepare'
    } elseif ($Action -eq 'start') {
        Invoke-DiscourseDocker start $Container
        $Processes = (Invoke-DiscourseDocker exec $Container ps -eo 'pid,args') -join "`n"
        if ($Processes -notmatch 'unicorn master') {
            Invoke-DiscourseDocker exec -d -u discourse -w /src -e UNICORN_WORKERS=1 -e UNICORN_PORT=3000 `
                -e UNICORN_PID_PATH=/tmp/waata-unicorn3000.pid $Container sh -ec `
                'mkdir -p log; exec bin/unicorn > log/waata-unicorn.log 2>&1'
        }
        if ($Processes -notmatch 'ember server') {
            Invoke-DiscourseDocker exec -d -u discourse -w /src -e JOBS=2 -e NODE_OPTIONS=--max-old-space-size=3072 `
                $Container sh -ec 'mkdir -p log; exec bin/ember-cli --host 0.0.0.0 > log/waata-ember.log 2>&1'
        }
        if ($Processes -notmatch '(^|\n)\s*\d+\s+(\S*/)?mailhog(\s|$)') {
            Invoke-DiscourseDocker exec -d -u discourse -w /src $Container sh -ec 'mkdir -p log; exec mailhog > log/waata-mail.log 2>&1'
        }
        Write-Output 'First compilation takes time. Run preflight after http://127.0.0.1:4200/login is interactive.'
    } elseif ($Action -eq 'logs') {
        Invoke-DiscourseDocker logs --tail 15 $Container
        Invoke-DiscourseDocker exec -u discourse -w /src $Container sh -c 'tail -n 20 log/waata-unicorn.log log/waata-ember.log'
    } elseif ($Action -eq 'stop') {
        Invoke-DiscourseDocker stop $Container
    } else {
        Invoke-DiscourseDocker ps -a --filter "name=^/$Container$"
    }
} finally { Pop-Location }
