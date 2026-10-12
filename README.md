



School Management System
CS492 – Computer Science Team Project II
Created by: Group 9
Aaron Sorensen, Nicholas Swanson,
Sean Spray, and Shanna Rather
October 11, 2026

 Table of Contents
1.	Project Vision and Description	3
2.	Team Roles	3
3.	Collaboration Methodology	4
4.	The Definition of “Done”	4
5.	Product Design	6
6.	Sprint 1 Retrospective Summary Report	10
7.	Sprint 2 Retrospective Summary Report	11
8.	References	12



 1.	Project Vision and Description
The School Management System (SMS) is designed to bring all major school operations into one centralized platform. The system will support administrators, teachers, students, and parents by providing secure access to enrollment information, grades, attendance, schedules, and communication tools. The goal is to replace scattered manual processes with a unified digital solution that improves efficiency, accuracy, and collaboration across the school. During CS491, the requirements, high-level architecture, security plan, and sprint backlog were completed. In CS492, Group 9 will implement and test the system across two 2-week sprints (Sprint 1: October 6–19, 2026; Sprint 2: October 20–November 2, 2026), followed by a live demonstration in Week 5. This group version consolidates the members’ CS491 work, including Aaron Sorensen’s individual project document and sprint plan, the CS491 team’s consolidated security and architecture design, and Sean Spray’s Sprint 1 analysis of user roles, privacy, and sensitive data.
2.	Team Roles
Group 9 consists of four members: Aaron Sorensen, Nicholas Swanson, Shanna Rather, and Sean Spray. Nicholas Swanson joined team communication on October 12, 2026, and took on the Product Owner role and his Sprint 1 tasks. The team follows the Scrum framework to organize work and maintain clear responsibilities (Schwaber & Sutherland, 2020).
•	Product Owner – Nicholas Swanson: Manages the product backlog and ensures the team works on the highest-value features.
•	Scrum Master – Aaron Sorensen: Facilitates meetings, supports team communication, and removes obstacles.
•	Developers – Sean Spray and Shanna Rather: Implement, test, and document each sprint increment. Because the team is small, the Product Owner and Scrum Master also take on development tasks, and all members share ownership of code quality and security.
Each role contributes to delivering a secure, functional system while maintaining transparency and shared ownership of quality. Roles were rotated from CS491 so each member gains experience in a new Scrum role, and Sprint 1 tasks are claimed by individual members in the Sprint Planning workbook.
3.	Collaboration Methodology
Because team members have different schedules, the project uses both asynchronous and real-time communication. The team Discord server is used for day-to-day coordination and stand-up check-ins, while CTU group chat and email are used for official communication with the instructor. All members aim to reply within 24 hours to keep progress moving, reflecting the agile value of individuals and interactions over processes and tools (Beck et al., 2001).
Project documents are stored in a shared cloud folder to prevent version conflicts and ensure everyone can access the latest updates. Work is organized into sprints, each with a defined goal, selected backlog items, and a retrospective to evaluate what went well and what needs improvement. Source code is managed in a shared GitHub repository (github.com/aaronsorensen1988/School-Management-System), and each member records actual hours worked in the Sprint Planning workbook. Decisions are made collaboratively, with the Product Owner having final authority on scope and priorities.




4.	The Definition of “Done”
Requirements Met:
The deliverable fully addresses the acceptance criteria defined during sprint planning.
Peer Reviewed:
At least one team member other than the author has reviewed and approved the work.
Documentation Complete:
All relevant documentation has been updated to reflect the work completed.
Scope Verified:
The Product Owner has confirmed the deliverable aligns with the project vision and scope.
Submitted:
The deliverable has been submitted through the appropriate channel by the established deadline.
No Outstanding Issues:
 	Any identified issues or inconsistencies have been resolved or formally logged for a future sprint.
This Definition of Done applies to all group deliverables throughout CS492 and may be refined by the team as development progresses.
5.	Product Design
5.1 High Level Architecture
The system uses a multi-tier architecture (Sommerville, 2016):
•	Presentation Layer: Web/mobile UI (User Interface)
•	API Gateway: REST API, JWT validation
•	Business Logic Layer: UMA (User Management & Authentication), SIEM (Student Information & Enrollment Management), AMG (Academic Management & Gradebook), and CNS (Communication & Notification System) modules
•	Data Access Layer: ORM (Object Relational Mapping)/Repository
•	Database Layer: Encrypted relational database
•	Authentication Service: JWT/session manager
•	Notification Service: Email/SMS (Short Message Service) gateway
•	Security Suite: Firewall, IPS, SIEM, SOAR, EDR integrated across layers
The security design adds micro-segmentation, zero-trust principles, and monitoring across all tiers (Rose et al., 2020).
5.2 Security Centric Enhancements
Data Protection
•	AES 256 encryption at rest
•	TLS (Transport Layer Security) 1.3 with HSTS (HTTPS Strict Transport Security)
•	HSM/KMS (Hardware Security Module/Key Management System) key management
•	Data minimization
•	Immutable audit logs
Access Control
•	RBAC for roles (admin, teacher, student, parent)
•	ABAC for PHI (Personal Health Information) access (nurse, counselor)
•	Zero trust continuous authentication
Security Suite Integration
•	Firewall: DMZ (De-Militarized Zone), segmentation, geo blocking, application filtering
•	IPS: SQL injection prevention, anomaly detection
•	EDR: Device posture checks, ransomware rollback
•	SIEM: Log aggregation, correlation, compliance dashboards
•	SOAR: Automated incident response, PHI breach workflows
Compliance
•	FERPA (Family Educational Rights and Privacy Act)
•	HIPAA (Health Insurance Portability and Accountability Act)
•	NIST (National Institute of Standards and Technology) SP 800 53
•	NIST Zero Trust (800 207)
•	OWASP (Open Web Application Security Project) ASVS (Application Security Verification Standard)

 
Figure 1: High-Level System Architecture
Layer	Components	Description
Presentation Layer	Web Browser / Mobile Client	User-facing interface. Role-based dashboards for Admin, Teacher, Student, Parent. Communicates via HTTPS.
API Gateway	RESTful API Endpoints	Routes requests to appropriate service modules. Handles authentication token validation on every request.
Business Logic Layer	UMA Module, SIEM Module, AMG Module, CNS Module	Core application services. Each module corresponds to a sprint epic and operates independently.
Data Access Layer	ORM / Repository Pattern	Abstracts database operations. Enforces data validation and access control rules before any read/write.
Database Layer	Relational Database (e.g., PostgreSQL)	Persistent storage for all application data. Tables partitioned by module. Encrypted at rest.
Authentication Service	JWT Token Service / Session Manager	Issues and validates authentication tokens. Manages session expiration and role assignments.
Notification Service	Email/SMS Gateway	Sends outbound communications triggered by system events (grade posts, attendance, announcements).


The architecture uses a multi-tier web design with a presentation layer, API gateway, business logic modules, data access layer, and encrypted database. Security is integrated throughout the system, including FERPA compliance, encryption, audit logging, input validation, and role-based permissions.
Sprint 1 (October 6–19) delivers user management and authentication (UMA-001 to UMA-003), student profile enrollment (SIEM-004), and course scheduling (AMG-007). Sprint 2 (October 20–November 2) delivers attendance tracking, parent record access, grade entry, report cards, and the communication features (CNS-010 to CNS-012). All user stories are mapped to the design and to tasks in the Sprint Planning workbook. Sprint 1 was refined for Group 9 during Week 1: student enrollment (SIEM-004) and course scheduling (AMG-007) were moved into Sprint 1 in the product backlog to match the task plan, members claimed individual tasks, and capacity was adjusted to four team members.




 6.	Sprint 1 Retrospective Summary Report
Things That Went Well





Things That Could Have Gone Better




Things That Surprised Us




Lessons Learned







7.	Sprint 2 Retrospective Summary Report
Things That Went Well





Things That Could Have Gone Better




Things That Surprised Us



Lessons Learned








 8.	References

Beck, K., Beedle, M., van Bennekum, A., Cockburn, A., Cunningham, W., Fowler, M., Grenning, J., Highsmith, J., Hunt, A., Jeffries, R., Kern, J., Marick, B., Martin, R. C., Mellor, S., Schwaber, K., Sutherland, J., & Thomas, D. (2001). Manifesto for agile software development. https://agilemanifesto.org/
Rose, S., Borchert, O., Mitchell, S., & Connelly, S. (2020). Zero trust architecture (NIST Special Publication 800-207). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-207
Schwaber, K., & Sutherland, J. (2020). The Scrum guide: The definitive guide to Scrum: The rules of the game. https://scrumguides.org/scrum-guide.html
Sommerville, I. (2016). Software engineering (10th ed.). Pearson.

