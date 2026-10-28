"""Explicit avatar experiment opt-ins, outside the normal application suite.

No file is excluded by default pytest. --application-suite excludes these modules
only while their own declared opt-in is disabled. Dedicated avatar jobs select
and execute functional/browser/performance cases explicitly. Offline analysis
unit tests remain in the application suite; raw failures and archives stay intact.
"""

AVATAR_OPT_IN_SUITES = {'test_avatar_animal_batch_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_application_membership_browser.py': ('CSS_AVATAR_APP_MEMBERSHIP', '1'),
 'test_avatar_baseline_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_chase_writes_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_collection_attribution.py': ('CSS_AVATAR_COLLECTION_DIAGNOSTIC', '1'),
 'test_avatar_compositing_control.py': ('CSS_AVATAR_COMPOSITING_DIAGNOSTIC', '1'),
 'test_avatar_container_resize_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_cpu_attribution.py': ('CSS_AVATAR_CPU_DIAGNOSTIC', '1'),
 'test_avatar_geometry_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_interaction_diagnostic.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_layer_diagnostic.py': ('CSS_AVATAR_LAYER_DIAGNOSTIC', '1'),
 'test_avatar_lcp_diagnostic.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_lifecycle_allocation.py': ('CSS_AVATAR_ALLOCATION_DIAGNOSTIC', '1'),
 'test_avatar_motion_preference_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_native_attribution.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_native_control.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_navigation_cpu_browser.py': ('CSS_AVATAR_NAVIGATION_LIGHT', '1'),
 'test_avatar_navigation_light_browser.py': ('CSS_AVATAR_NAVIGATION_LIGHT', '1'),
 'test_avatar_navigation_residency_browser.py': ('CSS_AVATAR_NAVIGATION_RESIDENCY', '1'),
 'test_avatar_navigation_timing_browser.py': ('CSS_AVATAR_NAVIGATION_TIMING', '1'),
 'test_avatar_page_history_browser.py': ('CSS_AVATAR_PAGE_HISTORY', '1'),
 'test_avatar_pagehide_browser.py': ('CSS_AVATAR_LIFECYCLE', '1'),
 'test_avatar_pointer_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_preview_diagnostic.py': ('CSS_AVATAR_PREVIEW_DIAGNOSTIC', '1'),
 'test_avatar_profile_diagnostic.py': ('CSS_AVATAR_CPU_DIAGNOSTIC', '1'),
 'test_avatar_retaining_paths_browser.py': ('CSS_AVATAR_FORENSIC_GC', 'authorized'),
 'test_avatar_scheduler_diagnostic.py': ('CSS_AVATAR_SCHEDULER_DIAGNOSTIC', '1'),
 'test_avatar_server_diagnostic.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_shared_stylesheet_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_signal_diagnostic.py': ('CSS_AVATAR_CPU_DIAGNOSTIC', '1'),
 'test_avatar_snapshot_order_browser.py': ('CSS_AVATAR_SNAPSHOT_ORDER', '1'),
 'test_avatar_startup_diagnostic.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_static_preview_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_thread_pin_diagnostic.py': ('CSS_AVATAR_CPU_DIAGNOSTIC', '1'),
 'test_avatar_throttle_control.py': ('CSS_AVATAR_THROTTLE_DIAGNOSTIC', '1'),
 'test_avatar_trace_overhead.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_avatar_visual_state_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_cat_gradient_sharing_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_companion_customizer_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_home_search_boot_browser.py': ('CSS_AVATAR_BASELINE', '1'),
 'test_membership_lifecycle_transport_browser.py': ('CSS_MEMBERSHIP_TRANSPORT', '1')}
