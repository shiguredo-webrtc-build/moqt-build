#include <quiche/quic/moqt/moqt_bitrate_adjuster.h>
#include <quiche/quic/moqt/moqt_fetch_task.h>
#include <quiche/quic/moqt/moqt_framer.h>
#include <quiche/quic/moqt/moqt_known_track_publisher.h>
#include <quiche/quic/moqt/moqt_live_relay_queue.h>
#include <quiche/quic/moqt/moqt_messages.h>
#include <quiche/quic/moqt/moqt_object.h>
#include <quiche/quic/moqt/moqt_outgoing_queue.h>
#include <quiche/quic/moqt/moqt_parser.h>
#include <quiche/quic/moqt/moqt_priority.h>
#include <quiche/quic/moqt/moqt_probe_manager.h>
#include <quiche/quic/moqt/moqt_publisher.h>
#include <quiche/quic/moqt/moqt_relay_track_publisher.h>
#include <quiche/quic/moqt/moqt_session.h>
#include <quiche/quic/moqt/moqt_session_callbacks.h>
#include <quiche/quic/moqt/moqt_session_interface.h>
#include <quiche/quic/moqt/moqt_subscribe_windows.h>
#include <quiche/quic/moqt/moqt_track.h>
#include <quiche/quic/moqt/namespace_tree.h>

#include <iostream>
#include <vector>
#include <string>

int main() {
    std::cout << "MOQTライブラリ動作確認開始" << std::endl;
    
    // TrackNamespaceのテスト (absl::string_viewを使用)
    moqt::TrackNamespace track_namespace({"test", "namespace", "example"});
    std::cout << "TrackNamespace作成成功: " << track_namespace.ToString() << std::endl;
    
    // FullTrackNameのテスト
    moqt::FullTrackName full_track_name(track_namespace, "track1");
    std::cout << "FullTrackName作成成功: " << full_track_name.ToString() << std::endl;
    
    // MoqtPriorityのテスト (uint8_t型)
    moqt::MoqtPriority subscriber_priority = 128;  // 中間の優先度
    moqt::MoqtPriority publisher_priority = 128;
    moqt::MoqtDeliveryOrder delivery_order = moqt::MoqtDeliveryOrder::kAscending;
    std::cout << "MoqtPriority作成成功 (subscriber=" << static_cast<int>(subscriber_priority) 
              << ", publisher=" << static_cast<int>(publisher_priority) << ")" << std::endl;
    
    // SubscribeWindowのテスト
    moqt::SubscribeWindow window(moqt::Location{1, 0}, moqt::Location{10, 0});
    moqt::Location start = window.start();
    moqt::Location end = window.end();
    std::cout << "SubscribeWindow作成成功 (start=[" 
              << start.group << "," << start.object 
              << "], end=[" << end.group << "," << end.object << "])" << std::endl;
    
    // MoqtObjectのテスト
    moqt::MoqtObject obj;
    obj.track_alias = 42;
    obj.group_id = 1;
    obj.object_id = 2;
    obj.publisher_priority = 128;
    obj.object_status = moqt::MoqtObjectStatus::kNormal;
    obj.subgroup_id = 0;
    obj.payload_length = 1024;
    std::cout << "MoqtObject作成成功 (track_alias=" << obj.track_alias 
              << ", group=" << obj.group_id 
              << ", object=" << obj.object_id << ")" << std::endl;
    
    // MoqtForwardingPreferenceのテスト
    moqt::MoqtForwardingPreference forwarding_pref = moqt::MoqtForwardingPreference::kSubgroup;
    std::cout << "MoqtForwardingPreference: " 
              << moqt::MoqtForwardingPreferenceToString(forwarding_pref) << std::endl;
    
    // MoqtSessionParametersのテスト
    moqt::MoqtSessionParameters params;
    params.version = moqt::kDefaultMoqtVersion;
    params.deliver_partial_objects = false;
    params.max_request_id = moqt::kDefaultInitialMaxRequestId;
    std::cout << "MoqtSessionParameters作成成功 (version=" 
              << static_cast<uint64_t>(params.version) 
              << ", max_request_id=" << params.max_request_id << ")" << std::endl;
    
    std::cout << "\n全てのテストが成功しました！" << std::endl;
    std::cout << "MOQTライブラリは正常に動作しています。" << std::endl;
    
    return 0;
}