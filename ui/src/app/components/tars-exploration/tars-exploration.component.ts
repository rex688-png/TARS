import { CommonModule } from "@angular/common";
import { Component, OnDestroy, OnInit, ViewChild } from "@angular/core";
import { Subscription } from "rxjs";
import { NavigationContainerComponent } from "../navigation-container/navigation-container.component";
import { ProjectionsService } from "../../services/projections.service";

/** A small exploration surface over authoritative journal projections. */
@Component({
  selector: "app-tars-exploration",
  standalone: true,
  imports: [CommonModule, NavigationContainerComponent],
  templateUrl: "./tars-exploration.component.html",
  styleUrl: "./tars-exploration.component.css",
})
export class TarsExplorationComponent implements OnInit, OnDestroy {
  @ViewChild(NavigationContainerComponent) navigation?: NavigationContainerComponent;
  location: Record<string, unknown> | null = null;
  navInfo: Record<string, unknown> | null = null;
  biology: Record<string, unknown> | null = null;
  private readonly subscriptions = new Subscription();

  constructor(private readonly projections: ProjectionsService) {}

  ngOnInit(): void {
    this.subscriptions.add(this.projections.location$.subscribe(value => this.location = value));
    this.subscriptions.add(this.projections.navInfo$.subscribe(value => this.navInfo = value));
    this.subscriptions.add(this.projections.exobiologyScan$.subscribe(value => this.biology = value));
  }
  ngOnDestroy(): void { this.subscriptions.unsubscribe(); }

  get route(): readonly Record<string, unknown>[] {
    return Array.isArray(this.navInfo?.["NavRoute"]) ? this.navInfo["NavRoute"] as Record<string, unknown>[] : [];
  }
  get destination(): string | null {
    const name = this.route.at(-1)?.["StarSystem"];
    return typeof name === "string" ? name : null;
  }
  get system(): string | null {
    return typeof this.location?.["StarSystem"] === "string" ? this.location["StarSystem"] as string : null;
  }
  get body(): string | null {
    return typeof this.location?.["Body"] === "string" ? this.location["Body"] as string : null;
  }
  get organism(): string | null {
    return typeof this.biology?.["life_form"] === "string" ? this.biology["life_form"] as string : null;
  }
  get sampleCount(): number | null {
    return Array.isArray(this.biology?.["scans"]) ? this.biology["scans"].length : null;
  }
  get notableWorlds(): readonly { name: string; reason: string }[] {
    return this.navigation?.getInterestingBodies().map(({ body, reasons }) => ({
      name: String(body?.name ?? body?.bodyName ?? "Recorded body"),
      reason: reasons.map(item => item.label).join(" · "),
    })) ?? [];
  }
  get biologicalBodies(): number { return this.navigation?.getBiologicalSignalBodies().length ?? 0; }
}
