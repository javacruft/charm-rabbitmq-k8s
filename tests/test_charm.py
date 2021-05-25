# Copyright 2021 David
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock

from charm import RabbitMQOperatorCharm
from ops.testing import Harness
import ops.model


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(RabbitMQOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_config_changed(self):
        self.assertEqual(list(self.harness.charm._stored.enabled_plugins), [])
        # Mock the file push
        self.harness.charm._render_and_push_config_files = Mock()
        self.harness.update_config({"enabled_plugins": "rabbitmq_management"})
        self.assertEqual(list(self.harness.charm._stored.enabled_plugins), ["rabbitmq_management"])

    def test_action(self):
        action_event = Mock()
        self.harness.charm._on_get_operator_info_action(action_event)

        self.assertTrue(action_event.set_results.called)

    def test_rabbitmq_pebble_ready(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("rabbitmq")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "rabbitmq-server": {
                    "override": "replace",
                    "summary": "RabbitMQ Server",
                    "command": "rabbitmq-server",
                    "startup": "enabled",
                },
            },
        }
        # Get the rabbitmq container from the model
        container = self.harness.model.unit.get_container("rabbitmq")
        # Emit the PebbleReadyEvent carrying the rabbitmq container
        self.harness.charm.on.rabbitmq_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("rabbitmq").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("rabbitmq").get_service("rabbitmq-server")
        self.assertTrue(service.is_running())

    def test_update_status(self):
        """This test validates the charm, the peers relation and the amqp relation.
        """
        self.harness.set_leader(True)
        self.harness.model.get_binding = Mock()
        self.harness.charm._get_admin_api = Mock()

        # Early not initialized
        self.harness.charm.on.update_status.emit()
        self.assertEqual(
            self.harness.model.unit.status,
            ops.model.WaitingStatus('Waiting to initialize operator user'))

        # RabbitMQ is up, operator user initialized
        peers_relation_id = self.harness.add_relation("peers", "rabbitmq-operator")
        self.harness.add_relation_unit(peers_relation_id, "rabbitmq-operator/0")
        self.harness.charm.on.update_status.emit()
        self.assertEqual(
            self.harness.model.unit.status,
            ops.model.WaitingStatus('Ready but waiting for an AMQP client relation.'))

        # AMQP relation incomplete
        amqp_relation_id = self.harness.add_relation("amqp", "amqp-client-app")
        self.harness.add_relation_unit(amqp_relation_id, "amqp-client-app/0")
        self.harness.charm.on.update_status.emit()
        self.assertEqual(
            self.harness.model.unit.status,
            ops.model.WaitingStatus('AMQP relation incomplete'))

        # AMQP relation complete
        self.harness.update_relation_data(
            amqp_relation_id, "amqp-client-app",
            {"username": "client",
             "vhost": "client-vhost"})
        self.harness.charm.on.update_status.emit()
        self.assertEqual(
            self.harness.model.unit.status,
            ops.model.ActiveStatus())
