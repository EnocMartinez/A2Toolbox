#!/usr/bin/env python3
"""


author: Enoc Martínez
institution: Universitat Politècnica de Catalunya (UPC)
email: enoc.martinez@upc.edu
license: MIT
created: 20/11/23
"""

from argparse import ArgumentParser
import serial
import rich
import socket
import time
import pandas as pd
import wave
from mutagen.id3 import ID3, TXXX
from mutagen.wave import WAVE
from threading import Thread


def add_id3_tags(filename, tags):
    t = time.time()
    wave = WAVE(filename)
    wave.add_tags()
    id3 = wave.tags
    for key, value in tags.items():
        # Add a custom TXXX frame to the ID3 tag
        id3.add(TXXX(encoding=3, desc=key, text=[value]))
    wave.save()
    rich.print(f"[purple]ID3 - Added tags to file {filename} took {1000*(time.time() - t):.02} msecs")



class NeXOS:
    def __init__(self):
        self.interface = None
        self.socket = None
        self.serial = None
        self.address = None


        # ---- RTSP Streams config ---- #
        self.streaming_port = 4002  # by default
        self.newSeqNum = -1
        self.oldSeqNum = -1
        self.rtpVersion = -1  # Version of the protocol
        self.rtpPayloadType = -1  # Format of the payload
        self.rtpSeqNum = -1  # The sequence number is incremented for each RTP data packet sent and is to be used by the receiver to detect packet loss
        self.rtpTimestampNs = -1  # ns Timestamp of the first sample in the packet
        self.rtpTimestampS = -1  # s Timestamp of the first sample in the packet
        self.packetSize = 1036
        self.samplesPerPacket = 512
        self.open_stream_port = False

        # ---- config info ---- #
        self.config_info = {}  # dict with the configuration

        self.ch = -1
        self.srate = -1
        self.gain_status = -1
        self.eq_status = -1

    # -------- Serial Port functions ---------- #
    def init_serial(self, device="/dev/ttyUSB0" ):
        """
        Initializes NeXOS A2 using the serial port
        :param device: serial device
        :return:
        """
        if self.serial:
            rich.print("[red]Serial already configured!")
            raise ValueError("Serial already configured!")

        self.serial = serial.Serial(port=device, baudrate=115200, timeout=1, bytesize=serial.EIGHTBITS,
                                    parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                    xonxoff=0,  # software flow control
                                    rtscts=0)  # hardware flow control

        if not self.interface:
            rich.print("Assigning serial port as default interface...")
            self.interface = "serial"

    def recv_serial(self, n=256):
        response = ""
        end = False
        time.sleep(0.1)
        while not end and len(response) < n:
            c = self.serial.read(1).decode()
            rich.print(f"[red]{c}", end="")
            response += c
            if response.endswith("\r\n"):
                end = True
        return response.replace("\r\n", "")

    def send_serial(self, cmd):
        if type(cmd) is str:
            cmd = cmd.encode()
        assert(type(cmd) == bytes)
        r = self.serial.write(cmd)
        time.sleep(0.2)
        return r

    # -------- UDP functions ---------- #

    def init_udp(self, ip_addr, port=7777):
        """
        Initializes NeXOS A2 using the serial port
        :param ip_addr: hydrophone ip
        :param port: tcp port
        :return:
        """
        rich.print("Establishing UDP connection...", end="")
        self.nexos_address = (ip_addr, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(2)

        self.socket.sendto(b"*idn?\n\r", self.nexos_address)
        data = self.recv_udp()
        rich.print(f"[green]done[white] {data}")

        if not self.interface:
            rich.print("Assigning udp as default interface...")
            self.interface = "udp"


    def recv_udp(self):
        buffer = ""
        end = f"\r\n"
        rn_found = False
        while not rn_found:
            data = self.socket.recv(1024)
            buffer += data.decode()

            if buffer[-2:] == end:
                rn_found = True
        return buffer.replace("\r\n", "")

    def send_udp(self, cmd):
        if type(cmd) is str:
            cmd = cmd.encode()

        assert(type(cmd) == bytes)
        self.socket.sendto(cmd, self.nexos_address)


    # --------- generic wrappers ---------- #
    def send(self, string):
        """
        Sends a string via udp or serial depending on the self.interface value
        :param string: string to be sent
        """
        assert(self.interface in ["udp", "serial"])

        cmd = f"{string}\r\n"
        if self.interface == "serial":
            self.send_serial(cmd.encode())
        elif self.interface == "udp":
            self.send_udp(cmd.encode())

    def recv(self, n=256) -> str:
        """
        Receive a message from UDP or serial port
        :param n:
        :return:
        """
        if self.interface == "udp":
            return self.recv_udp()
        elif self.interface == "serial":
            return self.recv_serial(n)
        else:
            rich.print("[red]interface not properly set!")

    def query(self, command: str) -> str:
        rich.print(f"[purple]  TX: '{command}'")
        self.send(command)
        r = self.recv()
        rich.print(f"[cyan]  RX: '{r}'")
        r = r.replace("\"", "")
        return r

    def set(self, param, value, enclose=False):
        if type(value) != str:
            value = str(value)
        if not enclose:
            cmd = f"{param} {value}"
        else:
            cmd = f"{param} \"{value}\""

        rich.print(f"[green]Setting {cmd}")
        self.send(cmd)
        time.sleep(0.2)
        returned_value = self.query(f"{param}?")
        if returned_value != value:
            rich.print(f"expected '{value}' got {returned_value}")
            raise ValueError(f"could not set param {param}!!")

    def set_interface(self, interface):
        """
        Select 'serial' or 'udp' interface
        :param interface: 'serial' or 'udp'
        """
        assert(interface in ["udp", "serial"])
        self.interface = interface

    # -------- High-level functions -------- #
    def set_recv_ip(self, ip_addr: str):
        """
        Sets the IP to send the streams
        :return:
        """
        assert (type(ip_addr) is str)
        self.set("SYSTem:COMMunicate:LAN:RADDRess", ip_addr, enclose=True)

    def set_recv_port(self, port):
        """
        Sets the port where streams will be sent
        """
        assert (type(port) is int)

        self.set("SYSTem:COMMunicate:LAN:RPORT", int(port))

    def get_ip(self) -> str:
        """
        Asks the hydrophone for its IP address
        :return:
        """
        return self.query("SYSTem:COMMunicate:LAN:ADDRess?")


    # ---- Sampling Rate ----- #
    def set_srate(self, srate: int):
        """
        Change sampling rate
        :param srate:
        :return:
        """
        __valid_srates = [100000, 50000, 200000]
        assert (type(srate) is int)
        assert (srate in __valid_srates)
        return self.set("CONFigure:ACQuire:SRATe", srate)


    def get_srate(self) -> int:
        """
        Get sampling rate
        :return: sampling rate as int
        """
        return int(self.query("CONFigure:ACQuire:SRATe?"))

    # -------- Channel selection --------- #
    def set_channel(self, ch: int):
        assert (ch in [1, 2])
        cmd = f"INPut{ch}:STATe"
        self.set(cmd, 1)

    def get_channel(self):
        cmd = f"INPut1:STATe?"
        r = self.query(cmd)
        if int(r) == 1:
            return 1
        else:
            return 2
    # -------- Channel 1 Gain -------- #
    def set_gain(self, value: bool):  # only channel 1
        assert(type(value) is bool)
        if value:
            self.set("INPut1:GAIN:STATe", 1)
        else:
            self.set("INPut1:GAIN:STATe", 0)

    def get_gain(self): # only channel 1
        return self.query("INPut1:GAIN:STATe?")

    # -------- Channel 1 Equalizer -------- #
    def set_equalizer(self, value: bool):  # only for channel 1
        assert (type(value) is bool)
        self.set("INPut1:EQUalizer:STATe", int(value))

    def get_equalizer(self)-> str: # only for channel 1
        return self.query("INPut1:EQUalizer:STATe?")


    # -------- WAV generator -------- #
    def msg(self, *args):
        rich.print("[blue]", *args)

    def warnmsg(self, *args):
        rich.print("[yellow]", *args)

    # Opens an UDP socket at @port to receive data from the hydrophone
    def open_stream(self, port):
        self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # open_stream socket
        self.stream_socket.bind(('', port))  # bind socket to port
        self.open_stream_port = True

    def close_stream(self):
        # self.msg("Closing UDP port....")
        self.stream_socket.close()
        self.open_stream_port = False

    def info(self):
        self.msg("Gain", self.gain, "dB")
        self.msg("Sampling Frequency", self.srate / 1000, "kHz")

    def bytes_to_int(bytes):
        result = 0
        for b in bytes:
            result = result * 256 + int(b)
        return result

    # Receives an UDP Stream, processes it and returns an ndarray
    # of. The offset is eliminated from the stream
    # if the raw flag is set, the offset is not suppressed
    def receivePacket(self):
        rawdata = self.stream_socket.recv(self.packetSize)
        self.rtpVersion = rawdata[0]
        self.rtpPayloadType = rawdata[1]
        self.rtpSeqNum = rawdata[2:4]
        self.rtpTimestampNs = rawdata[4:8]
        self.rtpTimestampS = rawdata[8:12]
        self.oldSeqNum = self.newSeqNum
        self.newSeqNum = int.from_bytes(self.rtpSeqNum, byteorder='big')
        if self.oldSeqNum == -1:
            self.oldSeqNum = self.newSeqNum - 1
        return rawdata[12:]

    # accumulates X seconds of data
    def write_wav(self, seconds, prefix="NeXOS_A2", close=True):
        if not self.config_info:
            self.config_info = self.get_config()
        # Calculate number of packets
        if self.open_stream_port == False:
            self.open_stream(self.streaming_port)

        npackets = int(seconds * self.srate / self.samplesPerPacket)
        self.msg("Acquiring during", seconds, "s (", npackets, "packets)")

        timestamp = pd.Timestamp.now(tz="utc")
        rich.print(f"new wav at time {timestamp}")
        filename = prefix + "_" + timestamp.strftime("%Y%m%d_%H%M%Sz") + ".wav"
        obj = wave.open(filename, 'w')
        obj.setnchannels(1)  # mono
        obj.setsampwidth(2)
        obj.setframerate(self.srate)
        totalPacketsCount = 0
        while totalPacketsCount < npackets:
            # dataRaw = append(dataRaw,hydrophone.receivePacket())
            newPacket = self.receivePacket()
            obj.writeframesraw(newPacket)
            totalPacketsCount += 1
            seqGap = self.newSeqNum - self.oldSeqNum
            if seqGap > 1:
                self.msg("Lost: ", seqGap, "packets")

        obj.close()
        if close:
            self.close_stream()

        # Add metadata in a seprate thread
        metadata_thread = Thread(target=add_id3_tags, args=(filename, self.config_info))
        metadata_thread.start()
        return 1

    # accumulates X seconds of data
    def write_wav_continuous(self, seconds, prefix="NeXOS_A2"):
        while True:
            self.write_wav(seconds, prefix=prefix)



    def get_config(self) -> dict:
        """
        returns a dict with the configuration
        """
        self.ch = self.get_channel()
        if self.ch == 1:
            self.eq_status = self.get_equalizer()
            self.gain_status = self.get_gain()
        else:
            self.eq_status = "na"
            self.gain_status = "na"

        self.srate = self.get_srate()

        config = {
            "name": self.query("*idn?"),
            "version": self.query("SYSTem:VERSion?"),
            "channel": self.ch,
            "srate": self.srate ,
            "gain": self.gain_status,
            "equalizer":self.eq_status
        }
        self.config_info = config
        return config

    def start_streaming(self):
        self.set_recv_port(self.streaming_port)
        self.get_config()  # reload config
        self.set("CONFigure:STATe", "RUN_CONTINUOUS")

    def stop_streaming(self):
        self.set("CONFigure:STATe", "STOP", enclose=False)

    def get_streaming(self):
        return self.query("CONFigure:STATe?")



if __name__ == "__main__":
    nexos = NeXOS()
    nexos.init_udp("192.168.3.220")
    nexos.get_config()
