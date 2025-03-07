FROM python
RUN pip3 install pipenv
RUN pipenv install
CMD ["pipenv","run","python", "./main.py"]
EXPOSE 5000