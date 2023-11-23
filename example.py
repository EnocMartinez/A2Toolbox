#!/usr/bin/env python3
"""

author: Enoc Martínez
institution: Universitat Politècnica de Catalunya (UPC)
email: enoc.martinez@upc.edu
license: MIT
created: 20/11/23
"""

from  nexosA2.nexos import NeXOS

nexos = NeXOS()

# Init UDP interface
nexos.init_udp("192.168.3.220", port=7777)
#nexos.init_serial()

nexos.stop_streaming()
nexos.set_recv_ip("192.168.3.4")
# nexos.set_recv_port(4002) # automatico

nexos.set_channel(1)
nexos.set_equalizer(False)
nexos.set_gain(True)
print("---> set SRATE")
nexos.set_srate(100000)
print("----------------------")
nexos.start_streaming()
nexos.write_wav(10, "100k_ch1")

nexos.stop_streaming()
nexos.set_channel(2)
nexos.start_streaming()
nexos.set_srate(200000)
nexos.write_wav(10, "200k_ch2")

nexos.set_channel(1)
nexos.set_equalizer(True)
nexos.set_gain(True)
nexos.start_streaming()
nexos.write_wav(10)

nexos.write_wav_continuous(5, "cont")



