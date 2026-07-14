# """
# BACKUP: TEST COVERAGE FOR CONFIGURING DOCKER LIMITS
# -----------------------------------------------------------------
# Cut from `tests/test_config_manager.py` and `tests/test_config_configure.py`.
# """
# def test_multitasking_config_persistence(temp_config_sandbox, cm):
#     cm.set_max_active_containers(5)
#     assert cm.get_max_active_containers() == 5

#     cm.set_max_total_containers(15)
#     assert cm.get_max_total_containers() == 15

#     cm.set_container_idle_timeout(45.5)
#     assert cm.get_container_idle_timeout() == 45.5

# def test_multitasking_config_boundary_clamping(temp_config_sandbox, cm):
#     cm.set_max_active_containers(-2)
#     assert cm.get_max_active_containers() == 1

#     cm.set_container_idle_timeout(-10.0)
#     assert cm.get_container_idle_timeout() == 0.1

# def test_update_sandbox_limits(mock_cm, out_chat):
#     # Verifies updating Docker limits handles updates cleanly
#     res = out_chat.update_sandbox_limits("1g", 30)
#     assert res["status"] == "success"
