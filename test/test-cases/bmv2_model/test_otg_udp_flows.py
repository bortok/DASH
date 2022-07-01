import snappi


def test_udp_bidirectional():
    """
    TODO update description
    This script does following:
    - Send 1000 packets from one port to another at a rate of
      1000 packets per second.
    - Validate that total packets sent are received on the same interface
    """
    # create a new API instance where location points to controller
    api = snappi.api(location="https://localhost", verify=False)
    # and an empty traffic configuration to be pushed to controller later on
    cfg = api.config()

    # add two ports where location points to traffic-engine (aka ports)
    p1, p2 = cfg.ports.port(name="p1", location="localhost:5555").port(
        name="p2", location="localhost:5556"
    )

    # add two traffic flows
    f1, f2 = cfg.flows.flow(name="p1->p2").flow(name="p2->p1")
    # and assign source and destination ports for each
    f1.tx_rx.port.tx_name, f1.tx_rx.port.rx_name = p1.name, p2.name
    f2.tx_rx.port.tx_name, f2.tx_rx.port.rx_name = p2.name, p1.name

    # configure packet size, rate and duration for both flows
    f1.size.fixed, f2.size.fixed = 128, 256
    pkt_count=500
    pps=50
    for f in cfg.flows:
        # send pkt_count packets and stop
        f.duration.fixed_packets.packets = pkt_count
        # send pps packets per second
        f.rate.pps = pps
        # enable flow metrics
        f.metrics.enable = True

    # configure packet with Ethernet, IPv4 and UDP headers for both flows
    eth1, ip1, udp1 = f1.packet.ethernet().ipv4().udp()
    eth2, ip2, udp2 = f2.packet.ethernet().ipv4().udp()
    
    # set source and destination MAC addresses
    eth1.src.value, eth1.dst.value = "00:AA:00:00:04:00", "00:AA:00:00:00:AA"
    eth2.src.value, eth2.dst.value = "00:AA:00:00:00:AA", "00:AA:00:00:04:00"
    
    # set source and destination IPv4 addresses
    ip1.src.value, ip1.dst.value = "10.0.0.1", "10.0.0.2"
    ip2.src.value, ip2.dst.value = "10.0.0.2", "10.0.0.1"
    
    # set incrementing port numbers as source UDP ports
    udp1.src_port.increment.start = 32768
    udp1.src_port.increment.step = 53
    udp1.src_port.increment.count = 100

    udp2.src_port.increment.start = 32768
    udp2.src_port.increment.step = 47
    udp2.src_port.increment.count = 100

    # set incrementing port numbers as destination UDP ports
    udp1.dst_port.increment.start = 1024
    udp1.dst_port.increment.step = 67
    udp1.dst_port.increment.count = 100

    udp2.dst_port.increment.start = 1024
    udp2.dst_port.increment.step = 71
    udp2.dst_port.increment.count = 100


    print("Pushing traffic configuration ...")
    api.set_config(cfg)

    print("Starting transmit on all configured flows ...")
    ts = api.transmit_state()
    ts.state = ts.START
    api.set_transmit_state(ts)

    print("Checking metrics on all configured flows ...")
    print("Flow Name\tExpected\tCurrent Tx\tCurrent Rx\tTx Rate\tRx Rate")
    assert wait_for(lambda: flow_metrics_ok(api, cfg), pkt_count / pps * 2), "Metrics validation failed!"

    print("Test passed !")


def metrics_ok(api, cfg):
    # create a port metrics request and filter based on port names
    req = api.metrics_request()
    req.port.port_names = [p.name for p in cfg.ports]
    # include only sent and received packet counts
    req.port.column_names = [req.port.FRAMES_TX, req.port.FRAMES_RX]

    # fetch port metrics
    res = api.get_metrics(req)
    # calculate total frames sent and received across all configured ports
    total_tx = sum([m.frames_tx for m in res.port_metrics])
    total_rx = sum([m.frames_rx for m in res.port_metrics])
    expected = sum([f.duration.fixed_packets.packets for f in cfg.flows])

    print("%d\t\t%d\t\t%d" % (expected, total_tx, total_rx))

    return expected == total_tx and total_rx >= expected

def flow_metrics_ok(api, cfg):
    # expectations per flow
    FlowExpectedDict = {}
    for f in cfg.flows:
        FlowExpectedDict.update({f.name: {'expected_packets': f.duration.fixed_packets.packets}})
    # create a flow metrics request
    req = api.metrics_request()
    req.flow.flow_names = [f.name for f in cfg.flows]
    
    # fetch metrics
    res = api.get_metrics(req)
    completed = True # will check if there are any flows that are still running below
    for fm in res.flow_metrics:
        expected = FlowExpectedDict[fm.name]['expected_packets']
        print("%s\t\t%d\t\t%d\t\t%d\t\t%d\t%d" % (fm.name, expected, fm.frames_tx, fm.frames_rx, fm.frames_tx_rate, fm.frames_rx_rate))
        if expected != fm.frames_tx or fm.frames_rx < fm.frames_tx:
            completed = False
    
    return completed


def wait_for(func, timeout=10, interval=0.2):
    """
    Keeps calling the `func` until it returns true or `timeout` occurs
    every `interval` seconds.
    """
    import time

    start = time.time()

    while time.time() - start <= timeout:
        if func():
            return True
        time.sleep(interval)

    print("Timeout occurred !")
    return False