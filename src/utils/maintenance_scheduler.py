import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import os
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

async def run_daily_data_update():
    """
    Run the data fetching script to update all coins data.
    """
    logger.info("Starting Daily Data Update Task...")
    try:
        # Run scripts/fetch_missing_data_slowly.py
        # Path relative to this file: ../../scripts/fetch_missing_data_slowly.py
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts/fetch_missing_data_slowly.py'))
        
        if not os.path.exists(script_path):
            logger.error(f"Data update script not found at {script_path}")
            return

        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info(f"Daily Data Update Completed Successfully.\n{stdout.decode()[:500]}...") # Log first 500 chars
        else:
            logger.error(f"Daily Data Update Failed.\n{stderr.decode()}")
    except Exception as e:
        logger.error(f"Error running Daily Data Update: {e}")

async def run_model_retraining():
    """
    Run the model retraining script.
    """
    logger.info("Starting 3-Day Model Retraining Task...")
    try:
        # Run src/models/train_multicoin.py
        # Path relative to this file: ../models/train_multicoin.py
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../models/train_multicoin.py'))
        
        if not os.path.exists(script_path):
             logger.error(f"Training script not found at {script_path}")
             return

        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info(f"Model Retraining Completed Successfully.\n{stdout.decode()[:500]}...")
        else:
            logger.error(f"Model Retraining Failed.\n{stderr.decode()}")
    except Exception as e:
        logger.error(f"Error running Model Retraining: {e}")

def register_maintenance_tasks(scheduler: AsyncIOScheduler):
    """
    Register maintenance tasks to the scheduler.
    """
    # Daily Data Update at 01:00 AM
    scheduler.add_job(
        run_daily_data_update,
        CronTrigger(hour=1, minute=0),
        id='daily_data_update',
        replace_existing=True
    )
    
    # Retrain Models every 3 days at 03:00 AM
    # Start tomorrow at 3 AM to avoid immediate run on restart
    scheduler.add_job(
        run_model_retraining,
        IntervalTrigger(days=3, start_date=datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)),
        id='model_retraining',
        replace_existing=True
    )
    
    logger.info("Maintenance tasks registered: Daily Data Update (01:00), Retraining (Every 3 days)")
