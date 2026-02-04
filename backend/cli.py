"""
Integrador CLI.

DX-01: Command-line interface for common operations.
"""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("CLI dependencies not installed. Run: pip install typer rich")
    sys.exit(1)

app = typer.Typer(
    name="integrador",
    help="Integrador Restaurant Management CLI",
    add_completion=False,
)
console = Console()


# =============================================================================
# Database Commands
# =============================================================================

@app.command()
def db_migrate(
    revision: str = typer.Argument("head", help="Migration revision target"),
):
    """Run database migrations."""
    console.print(f"[blue]Running migrations to: {revision}[/blue]")
    
    try:
        from alembic import command
        from alembic.config import Config
        
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, revision)
        console.print("[green]✓ Migrations complete[/green]")
    except Exception as e:
        console.print(f"[red]✗ Migration failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def db_seed(
    env: str = typer.Option("development", help="Environment to seed"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reseed"),
):
    """Seed database with test data."""
    console.print(f"[blue]Seeding database for: {env}[/blue]")
    
    if env == "production" and not force:
        console.print("[red]Cannot seed production without --force[/red]")
        raise typer.Exit(1)
    
    try:
        # Import seeder (you'll need to create this)
        # from scripts.seed import seed_database
        # seed_database(env)
        console.print("[yellow]Seeding not yet implemented[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Seeding failed: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Cache Commands
# =============================================================================

@app.command()
def cache_clear(
    pattern: str = typer.Argument("*", help="Key pattern to clear"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted"),
):
    """Clear Redis cache by pattern."""
    import asyncio
    
    async def _clear():
        from shared.infrastructure.events import get_redis_pool
        
        redis = await get_redis_pool()
        
        # Find matching keys
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)
        
        if not keys:
            console.print("[yellow]No keys match pattern[/yellow]")
            return
        
        table = Table(title=f"Keys matching '{pattern}'")
        table.add_column("Key", style="cyan")
        
        for key in keys[:50]:  # Show first 50
            table.add_row(key)
        
        if len(keys) > 50:
            table.add_row(f"... and {len(keys) - 50} more")
        
        console.print(table)
        
        if dry_run:
            console.print(f"[yellow]Would delete {len(keys)} keys (dry run)[/yellow]")
        else:
            deleted = await redis.delete(*keys)
            console.print(f"[green]✓ Deleted {deleted} keys[/green]")
    
    asyncio.run(_clear())


@app.command()
def cache_warm():
    """Pre-warm all caches."""
    import asyncio
    
    async def _warm():
        from shared.infrastructure.events import get_redis_pool
        from shared.infrastructure.db import SessionLocal
        from shared.infrastructure.cache import warm_caches_on_startup
        
        redis = await get_redis_pool()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Warming caches...", total=None)
            await warm_caches_on_startup(redis, SessionLocal)
        
        console.print("[green]✓ Cache warming complete[/green]")
    
    asyncio.run(_warm())


@app.command()
def cache_stats():
    """Show Redis cache statistics."""
    import asyncio
    
    async def _stats():
        from shared.infrastructure.events import get_redis_pool
        
        redis = await get_redis_pool()
        info = await redis.info()
        
        table = Table(title="Redis Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Version", info.get("redis_version", "?"))
        table.add_row("Connected Clients", str(info.get("connected_clients", "?")))
        table.add_row("Used Memory", info.get("used_memory_human", "?"))
        table.add_row("Peak Memory", info.get("used_memory_peak_human", "?"))
        table.add_row("Total Keys", str(await redis.dbsize()))
        table.add_row("Uptime (days)", str(info.get("uptime_in_days", "?")))
        
        console.print(table)
    
    asyncio.run(_stats())


# =============================================================================
# DLQ Commands
# =============================================================================

@app.command()
def dlq_stats():
    """Show Dead Letter Queue statistics."""
    import asyncio
    
    async def _stats():
        from shared.infrastructure.events import get_redis_pool
        from shared.infrastructure.events.dlq_processor import DeadLetterProcessor
        
        redis = await get_redis_pool()
        processor = DeadLetterProcessor(redis)
        
        stats = await processor.get_dlq_stats()
        
        table = Table(title="DLQ Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Message Count", str(stats["message_count"]))
        table.add_row("Oldest Message", str(stats["oldest_message"] or "N/A"))
        
        if stats["error_breakdown"]:
            console.print(table)
            
            error_table = Table(title="Error Breakdown")
            error_table.add_column("Error Type", style="red")
            error_table.add_column("Count", style="yellow")
            
            for error_type, count in stats["error_breakdown"].items():
                error_table.add_row(error_type, str(count))
            
            console.print(error_table)
        else:
            console.print(table)
            console.print("[green]✓ No errors in DLQ[/green]")
    
    asyncio.run(_stats())


@app.command()
def dlq_process(
    max_messages: int = typer.Option(100, help="Max messages to process"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Analyze without processing"),
):
    """Process Dead Letter Queue messages."""
    import asyncio
    
    async def _process():
        from shared.infrastructure.events import get_redis_pool
        from shared.infrastructure.events.dlq_processor import DeadLetterProcessor
        
        redis = await get_redis_pool()
        processor = DeadLetterProcessor(redis)
        
        results = await processor.process_dlq(
            max_messages=max_messages,
            dry_run=dry_run,
        )
        
        table = Table(title="DLQ Processing Results")
        table.add_column("Action", style="cyan")
        table.add_column("Count", style="green")
        
        table.add_row("Retried", str(results["retried"]))
        table.add_row("Archived", str(results["archived"]))
        table.add_row("Skipped", str(results["skipped"]))
        
        console.print(table)
        
        if dry_run:
            console.print("[yellow]This was a dry run - no changes made[/yellow]")
    
    asyncio.run(_process())


# =============================================================================
# WebSocket Commands
# =============================================================================

@app.command()
def ws_test(
    url: str = typer.Option("ws://localhost:8001/ws/health", help="WebSocket URL"),
):
    """Test WebSocket connectivity."""
    import asyncio
    
    async def _test():
        try:
            import websockets
        except ImportError:
            console.print("[red]websockets not installed. Run: pip install websockets[/red]")
            return
        
        console.print(f"[blue]Testing WebSocket: {url}[/blue]")
        
        try:
            async with websockets.connect(url, close_timeout=5) as ws:
                # Send ping
                await ws.send('{"type": "ping"}')
                response = await asyncio.wait_for(ws.recv(), timeout=5)
                console.print(f"[green]✓ Connected! Response: {response}[/green]")
        except asyncio.TimeoutError:
            console.print("[red]✗ Connection timed out[/red]")
        except Exception as e:
            console.print(f"[red]✗ Connection failed: {e}[/red]")
    
    asyncio.run(_test())


# =============================================================================
# Health Commands
# =============================================================================

@app.command()
def health():
    """Check system health."""
    import asyncio
    import httpx
    
    async def _health():
        services = [
            ("REST API", "http://localhost:8000/health"),
            ("WS Gateway", "http://localhost:8001/health"),
        ]
        
        table = Table(title="Service Health")
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Response Time", style="yellow")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in services:
                try:
                    import time
                    start = time.time()
                    response = await client.get(url)
                    elapsed = (time.time() - start) * 1000
                    
                    if response.status_code == 200:
                        table.add_row(name, "✓ Healthy", f"{elapsed:.0f}ms")
                    else:
                        table.add_row(name, f"✗ Status {response.status_code}", f"{elapsed:.0f}ms")
                except Exception as e:
                    table.add_row(name, f"✗ {type(e).__name__}", "-")
        
        # Check Redis
        try:
            from shared.infrastructure.events import get_redis_pool
            import time
            start = time.time()
            redis = await get_redis_pool()
            await redis.ping()
            elapsed = (time.time() - start) * 1000
            table.add_row("Redis", "✓ Healthy", f"{elapsed:.0f}ms")
        except Exception as e:
            table.add_row("Redis", f"✗ {type(e).__name__}", "-")
        
        console.print(table)
    
    asyncio.run(_health())


@app.command()
def version():
    """Show version information."""
    table = Table(title="Integrador Version")
    table.add_column("Component", style="cyan")
    table.add_column("Version", style="green")
    
    table.add_row("API", "2.0.0")
    table.add_row("CLI", "1.0.0")
    table.add_row("Python", sys.version.split()[0])
    
    console.print(table)


if __name__ == "__main__":
    app()
