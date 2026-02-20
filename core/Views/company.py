# views.py

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from core.models import Company
from core.serializers import CompanySerializer


def _generate_next_company_id():
    """Auto-generate next company_id in format CHC001, CHC002, ..."""
    last_company = Company.objects.filter(
        company_id__startswith="CHC"
    ).order_by("-company_id").first()

    if last_company:
        try:
            num = int(last_company.company_id[3:]) + 1
        except ValueError:
            num = 1
    else:
        num = 1

    return f"CHC{num:03d}"


@api_view(["GET"])
def get_next_company_id(request):
    """Return the next auto-generated company_id."""
    return Response({"company_id": _generate_next_company_id()})


@api_view(["GET", "POST"])
def company_list_create(request):
    if request.method == "GET":
        companies = Company.objects.all()
        serializer = CompanySerializer(companies, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        data = request.data.copy()
        # Auto-generate company_id if not provided
        if not data.get("company_id"):
            data["company_id"] = _generate_next_company_id()

        serializer = CompanySerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PATCH"])
def company_detail(request, pk):
    try:
        company = Company.objects.get(pk=pk)
    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = CompanySerializer(company)
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
