import os
import time
import sys
import logging

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the parent directory to the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ppmac import pp_comm

from ppmac import gather
from ppmac.pp_comm import PPComm
import ppmac.config as config
from ppmac.util import InsList

import numpy as np


fast_gather_port = 0

logger.debug('Power PMAC default host: %s:%d', config.hostname, config.port)
logger.debug('Power PMAC default login: %s/%s', config.username, config.password)


def run_script_and_gather(gpascii, script_gather=[],
                   gather_vars=[], period=1, samples=gather.max_samples,
                   pre_script=None, pos_script=None,
                   timed_script=None, run_time=10, gather_timeout=60,
                   cancel_callback=None, check_active=False,
                   verbose=True):

    """
    Run text script and read back the gathered data
    """


    if 'gather.enable' not in script_gather.lower():
        script_gather = '\n'.join(['gather.enable=2',
                                 script_gather,
                                 ])

    if pre_script is not None:
        script_gather = '\n'.join([pre_script,
                                 script_gather,
                                 ])

    comm = gpascii._comm
    gpascii.set_variable('gather.enable', '0')

    gather_vars = InsList(gather_vars)

    if 'sys.servocount.a' not in gather_vars:
        gather_vars.insert(0, 'Sys.ServoCount.a')

    settings = gather.get_settings(gpascii.servo_period, gather_vars,
                            gather_period=period,
                            samples=samples)

    settings = '\n'.join(settings)

    comm.write_file(gather.gather_config_file, settings)

    logger.info('Wrote configuration to %s', gather.gather_config_file)

    comm.gpascii_file(gather.gather_config_file, verbose=verbose)

    for line in script_gather.split('\n'):
        print(line)
        gpascii.send_line(line.lstrip())

    if check_active:
        active_var = 'gather.enable'
    else:
        active_var = 'gather.enable'

    def get_status():
        return gpascii.get_variable(active_var, type_=int)

    try:
        pp_comm.vlog(verbose, "Waiting...")
        while get_status() == 0:
            time.sleep(0.1)

        t0 = time.time()
        while get_status() != 0 and (time.time() - t0) < gather_timeout:
            if timed_script and (time.time() - t0) >= run_time:
                for line in timed_script.split('\n'):
                    gpascii.send_line(line.lstrip())
            samples = gpascii.get_variable('gather.samples', type_=int)
            pp_comm.vlog(verbose, "Working... got %6d data points - Elapsed time: %d seconds" % (samples,(time.time() - t0)), end='\r')
            time.sleep(0.1)

        # Check if the timeout was reached
        if get_status() != 0 and (time.time() - t0) >= gather_timeout:
            gpascii.send_line('gather.enable=0')
            pp_comm.vlog(verbose, "\nTime out")

        pp_comm.vlog(verbose, '\nDone')

    except KeyboardInterrupt as ex:
        pp_comm.vlog(verbose, 'Cancelled - stopping program')
        #gpascii.kill_motor(motor)
        if pos_script is not None:
            for line in pos_script.split('\n'):
                gpascii.send_line(line.lstrip())
        if cancel_callback is not None:
            cancel_callback(ex)

    try:
        for line in gpascii.read_timeout(timeout=0.1):
            if 'error' in line:
                if verbose:
                    print(line)
                logger.error(line)
    except pp_comm.TimeoutError:
        pass

    if pos_script is not None:
        for line in pos_script.split('\n'):
            gpascii.send_line(line.lstrip())

    return gather_vars


def main():

    pre_script =''

    script ='''gather.enable=2
    #1j=1000'''

    timed_script=''

    pos_script=''

    config.hostname = os.environ.get('PPMAC_HOST', '172.23.59.7')
    config.port = int(os.environ.get('PPMAC_PORT', '22'))
    config.username = os.environ.get('PPMAC_USER', 'root')
    config.password = os.environ.get('PPMAC_PASS', 'deltatau')

    try:
        logging.basicConfig()
        logger.setLevel(logging.WARNING)
        comm = PPComm(config.hostname, config.port, config.username, config.password)
        gpascii = comm.gpascii_channel()
        servo_period = gpascii.servo_period
        print(servo_period)
        gather_period = 1
        gather_duration = 3 # seconds
        run_time = 2 # seconds

        gather_samples = gather.get_sample_count(servo_period, gather_period, gather_duration)
        if(gather_samples>500000):
            gather_samples = 500000
        gather_duration = gather_samples*servo_period
        print(f"Gather samples: {gather_samples}")
        print(f"Gather duration: {gather_duration}")

        gather_vars = ['Sys.ServoCount.a',
                    'Motor[1].DesPos.a',
                    'Motor[1].ActPos.a']

        run_script_and_gather(gpascii, script, gather_vars, period=gather_period, samples=gather_samples, pre_script=pre_script, pos_script=pos_script, timed_script=timed_script, run_time=run_time)
        gather_output_file = '/var/ftp/gather/GatherFile.txt'
        data = gather.get_gather_results(gpascii._comm,gather_vars,gather_output_file)
        gather.gather_data_to_file('test.txt', gather_vars, data)

        gather.plot(gather_vars, data)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        gpascii = None
    finally:

        if gpascii is not None:
            gpascii.close()

        print("Finally")
if __name__ == '__main__':
    main()