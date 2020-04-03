#!/usr/bin/env python3
import json
import re
import socket
import struct
import subprocess

from gi.repository import GLib

from notification import Urgency, Notification


def linesplit(socket):
    buffer = socket.recv(16)
    buffer = buffer.decode("UTF-8")
    buffering = True
    while buffering:
        if '\n' in buffer:
            (line, buffer) = buffer.split("\n", 1)
            yield line
        else:
            more = socket.recv(16)
            more = more.decode("UTF-8")
            if not more:
                buffering = False
            else:
                buffer += more
    if buffer:
        yield buffer

rofi_command = [ 'rofi' , '-dmenu', '-p', 'Notifications', '-markup']

def strip_tags(value):
  "Return the given HTML with all tags stripped."
  return re.sub(r'<[^>]*?>', '', value)

def call_rofi(entries, additional_args=[]):
    additional_args.extend([ '-kb-accept-entry', 'Control+j,Control+m,KP_Enter',
                             '-kb-remove-char-forward', 'Control+d',
                             '-kb-delete-entry', '',
                             '-kb-custom-1', 'Delete',
                             '-kb-custom-2', 'Return',
                             '-kb-custom-3', 'Alt+r',
                             '-kb-custom-4', 'Shift+Delete',
                             '-markup-rows',
                             '-sep', '\\0',
                             '-format', 'i',
                             '-eh', '2',
                             '-lines', '10'])
    proc = subprocess.Popen(rofi_command+ additional_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for e in entries:
        proc.stdin.write((e).encode('utf-8'))
        proc.stdin.write(struct.pack('B', 0))
    proc.stdin.close()
    answer = proc.stdout.read().decode("utf-8")
    exit_code = proc.wait()
    # trim whitespace
    if answer == '':
        return None,exit_code
    else:
        return int(answer),exit_code


def send_command(cmd):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect("/tmp/rofi_notification_daemon")
    print("Send: {cmd}".format(cmd=cmd))
    client.send(bytes(cmd, 'utf-8'))
    client.close()


did = None
cont=True
while cont:
    cont=False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect("/tmp/rofi_notification_daemon")
    client.send(b"list",4)
    ids=[]
    entries=[]
    index=0
    urgent=[]
    low=[]
    args=[]
    for a in linesplit(client):
        if len(a) > 0:
            notification = json.loads(a, object_hook=Notification.make)
            ids.append(notification)
            mst = ("<b>{summ}</b> <small>({app})</small>\n<small>{body}</small>".format(
                   summ=GLib.markup_escape_text(strip_tags(notification.summary)),
                   app=GLib.markup_escape_text(strip_tags(notification.application)),
                   body=GLib.markup_escape_text(strip_tags(notification.body.replace("\n", " ")))))
            entries.append(mst)
            if Urgency(notification.urgency) is Urgency.CRITICAL:
                urgent.append(str(index))
            if Urgency(notification.urgency) is Urgency.LOW:
                low.append(str(index))
            index+=1
    if len(urgent):
        args.append("-u")
        args.append(",".join(urgent))
    if len(low):
        args.append("-a")
        args.append(",".join(low))

    # Select previous selected row.
    if did != None:
        args.append("-selected-row")
        args.append(str(did))
    # Show rofi
    did, code = call_rofi(entries, args)
    # print("{a},{b}".format(a=did,b=code))
    if did is None or did < 0:
        break
    # Dismiss notification
    if code == 10:
        send_command("del:{mid}".format(mid=ids[did].id))
        cont=True
    # Seen notification
    elif code == 11:
        send_command("saw:{mid}".format(mid=ids[did].id))
        cont=True
    elif code == 12:
        cont=True
    # Dismiss all notifications for application
    elif code == 13:
        send_command("dela:{app}".format(app=ids[did].application))
        cont=True
