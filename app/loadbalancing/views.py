from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.loadbalancing.node_info import node_info_payload
from app.loadbalancing.routing_service import (
    bin_decisions_snapshot,
    route_decision,
    routing_table_snapshot,
    server_snapshots,
)


class NodeInfoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(node_info_payload())


class LoadDistributionServersView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(server_snapshots())


class LoadDistributionTableView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(routing_table_snapshot())


class LoadDistributionDecisionsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(bin_decisions_snapshot())


class LoadDistributionRouteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        expected = request.data.get('expectedComputeUnits')
        if expected is None:
            return Response({'detail': 'expectedComputeUnits is required'}, status=400)
        try:
            units = float(expected)
        except (TypeError, ValueError):
            return Response({'detail': 'expectedComputeUnits must be numeric'}, status=400)
        if units <= 0:
            return Response({'detail': 'expectedComputeUnits must be > 0'}, status=400)
        return Response(route_decision(units))
