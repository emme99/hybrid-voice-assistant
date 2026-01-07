
from aioesphomeapi import api_pb2

print(f"HelloRequest: {api_pb2.HelloRequest().MESSAGE_TYPE_ID if hasattr(api_pb2.HelloRequest, 'MESSAGE_TYPE_ID') else '?'}")
# Actually usually it's not ID on the class, but we need to map them. 
# Let's inspect how aioesphomeapi maps them. 
# Or just assume the standard IDs:
# 1: HelloRequest
# 2: HelloResponse
# 3: ConnectRequest
# 4: ConnectResponse
# 5: DisconnectRequest
# 6: DisconnectResponse
# 9: DeviceInfoRequest
# 10: DeviceInfoResponse
# 11: ListEntitiesRequest
# 12: ListEntitiesDoneResponse
# 20: SubscribeStatesRequest
# ...
# Voice Assistant ones?
print("Checking VoiceAssistantAudio ID...")
try:
    print(f"VoiceAssistantAudio: {api_pb2.VoiceAssistantAudio.id if hasattr(api_pb2.VoiceAssistantAudio, 'id') else 'Not found'}")
except:
    pass
